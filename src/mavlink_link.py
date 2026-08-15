"""pymavlink 로 비행 컨트롤러(MicoAir 743 v2 / ArduCopter)와 통신하는 모듈.

이 예제는 절대 스스로 시동을 걸거나 이륙하지 않습니다.
  1. 조종자가 조종기로 시동 + 이륙 (Position 등)
  2. 조종자가 GUIDED 모드로 전환
  3. 그때부터 이 스크립트가 속도 명령을 보냄
  4. 조종기로 모드를 빼면 즉시 조종자에게 제어권이 돌아감  <- 항상 가능

ArduCopter GUIDED 모드에서는 SET_POSITION_TARGET_LOCAL_NED 속도 명령을 받습니다.
이 모듈은 MAV_FRAME_BODY_OFFSET_NED 를 사용하므로 Command 의 전/우/아래 속도를
기체 기수 기준으로 그대로 보낼 수 있습니다.

속도 명령이 GUID_TIMEOUT(기본 3초) 동안 끊기면 ArduCopter가 정지하므로, 카메라
속도와 무관하게 send_rate 주기로 계속 명령을 보냅니다. 단, 이 모듈은 안전상
스스로 시동하거나 GUIDED 모드로 바꾸지 않습니다.
"""

import time

from pymavlink import mavutil

from command import Command

# SET_POSITION_TARGET_LOCAL_NED 에서 "속도 + yaw_rate 만 쓴다"는 뜻의 비트마스크.
# 위치/가속도/yaw 각도 비트를 전부 무시(1)로 켠 값입니다.
VELOCITY_YAWRATE_MASK = 0b0000010111000111

# 기체 기준 좌표계 (+X 전방, +Y 오른쪽, +Z 아래).
FRAME_BODY_OFFSET_NED = mavutil.mavlink.MAV_FRAME_BODY_OFFSET_NED

# ArduCopter HEARTBEAT custom_mode 값. 지원하지 않는 모드는 숫자로 표시합니다.
ARDUCOPTER_MODES = {
    0: "STABILIZE",
    1: "ACRO",
    2: "ALT_HOLD",
    3: "AUTO",
    4: "GUIDED",
    5: "LOITER",
    6: "RTL",
    7: "CIRCLE",
    9: "LAND",
    11: "DRIFT",
    13: "SPORT",
    14: "FLIP",
    15: "AUTOTUNE",
    16: "POSHOLD",
    17: "BRAKE",
    18: "THROW",
    19: "AVOID_ADSB",
    20: "GUIDED_NOGPS",
    21: "SMART_RTL",
    22: "FLOWHOLD",
    23: "FOLLOW",
    24: "ZIGZAG",
    25: "SYSTEMID",
    26: "AUTOROTATE",
    27: "AUTO_RTL",
    28: "TURTLE",
}


def arducopter_mode_string(msg):
    """ArduCopter HEARTBEAT -> 모드 이름."""
    if msg.autopilot != mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA:
        return "UNSUPPORTED_AUTOPILOT"
    if not msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED:
        return "UNKNOWN"
    return ARDUCOPTER_MODES.get(msg.custom_mode, f"MODE({msg.custom_mode})")


class MavlinkLink:
    def __init__(self, cfg):
        m = cfg["mavlink"]
        s = cfg["safety"]
        self.dry_run = s["dry_run"]
        self.require_guided = s["require_guided"]
        self.require_armed = s["require_armed"]

        print(f"[MAVLink] 연결 중: {m['connection']} ...")
        self.master = mavutil.mavlink_connection(m["connection"], baud=m["baud"])
        self.master.wait_heartbeat()
        print(f"[MAVLink] 연결됨 (system {self.master.target_system})")

        self._armed = False
        self._mode = ""
        self._last_heartbeat = 0.0

    # ---------- 상태 ----------

    def poll(self):
        """쌓인 HEARTBEAT를 비우면서 모드와 시동 상태를 갱신합니다."""
        while True:
            msg = self.master.recv_match(type="HEARTBEAT", blocking=False)
            if msg is None:
                break
            # 지상국이나 다른 기기의 하트비트는 무시합니다.
            if msg.get_srcSystem() != self.master.target_system:
                continue
            self._armed = bool(
                msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
            )
            self._mode = arducopter_mode_string(msg)

        self._send_heartbeat()

    def _send_heartbeat(self):
        """ArduCopter가 컴패니언 링크를 감시할 수 있도록 1Hz heartbeat 전송."""
        if self.dry_run:
            return
        now = time.monotonic()
        if now - self._last_heartbeat < 1.0:
            return
        self._last_heartbeat = now
        self.master.mav.heartbeat_send(
            mavutil.mavlink.MAV_TYPE_ONBOARD_CONTROLLER,
            mavutil.mavlink.MAV_AUTOPILOT_INVALID,
            0, 0, 0,
        )

    @property
    def armed(self):
        return self._armed

    @property
    def mode(self):
        return self._mode

    def ready_to_command(self):
        """지금 속도 명령을 보내도 되는 상태인지."""
        if self.require_armed and not self._armed:
            return False, "시동 대기중"
        if self.require_guided and self._mode != "GUIDED":
            return False, f"GUIDED 아님 (현재 {self._mode or '?'})"
        return True, "OK"

    # ---------- 명령 ----------

    def send_velocity(self, cmd):
        """Command의 기체 기준 속도와 yaw rate를 ArduCopter에 전송."""
        if self.dry_run:
            return

        self.master.mav.set_position_target_local_ned_send(
            int(time.monotonic() * 1000) & 0xFFFFFFFF,  # time_boot_ms
            self.master.target_system,
            self.master.target_component,
            FRAME_BODY_OFFSET_NED,
            VELOCITY_YAWRATE_MASK,
            0, 0, 0,                                    # x, y, z (무시)
            cmd.forward, cmd.right, cmd.down,           # vx, vy, vz [m/s]
            0, 0, 0,                                    # afx, afy, afz (무시)
            0,                                          # yaw (무시)
            cmd.yaw_rate * 0.017453292519943295,         # yaw_rate [rad/s]
        )

    def send_stop(self):
        self.send_velocity(Command())

    def statustext(self, text):
        """지상국(Mission Planner 등) 화면에 메시지를 띄웁니다."""
        if self.dry_run:
            return
        self.master.mav.statustext_send(
            mavutil.mavlink.MAV_SEVERITY_INFO, text.encode()[:50]
        )
