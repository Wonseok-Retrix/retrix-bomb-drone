"""pymavlink 로 비행 컨트롤러(MicoAir 743 v2 / PX4)와 통신하는 모듈.

이 예제는 절대 스스로 시동을 걸거나 이륙하지 않습니다.
  1. 조종자가 조종기로 시동 + 이륙 (Position 등)
  2. 조종자가 OFFBOARD 모드로 전환
  3. 그때부터 이 스크립트가 속도 명령을 보냄
  4. 조종기로 모드를 빼면 즉시 조종자에게 제어권이 돌아감  <- 항상 가능

PX4 를 쓸 때 ArduPilot 과 다른 점 세 가지만 기억하세요.

  1. OFFBOARD 는 "들어가기 전에" 이미 setpoint 가 흐르고 있어야 진입이 승인됩니다.
     그래서 이 클래스는 모드/시동과 무관하게 항상 (정지) 명령을 계속 흘려보냅니다.
     ※ dry_run=True 면 아무것도 안 나가므로 OFFBOARD 진입 자체가 안 됩니다.
        지상 테스트에서 OFFBOARD 를 넣어보려면 --live 로 실행해야 합니다.

  2. 명령이 끊기면 PX4 는 COM_OF_LOSS_T (기본 1초) 만에 OFFBOARD 를 빠져나갑니다.
     ArduPilot 의 3초보다 훨씬 빡빡하므로 send_rate 를 낮추지 마세요.

  3. PX4 는 기체 기준 좌표계(BODY_NED) 속도 setpoint 를 안정적으로 받아주지
     않습니다. 그래서 여기서는 지구 기준(LOCAL_NED) 으로 보내되,
     기체 기수 방향(yaw)을 받아 화면 기준 명령을 직접 회전시켜 넣습니다.
     yaw 를 아직 못 받았으면 명령을 보내지 않습니다(= 안전).
"""

import math
import time

from pymavlink import mavutil

from command import Command

# SET_POSITION_TARGET_LOCAL_NED 에서 "속도 + yaw_rate 만 쓴다"는 뜻의 비트마스크.
# 위치/가속도/yaw 각도 비트를 전부 무시(1)로 켠 값입니다.
VELOCITY_YAWRATE_MASK = 0b0000010111000111

# 지구 기준 좌표계 (+X 북, +Y 동, +Z 아래).
# PX4 는 이 프레임의 속도 setpoint 를 가장 확실하게 받아줍니다.
FRAME_LOCAL_NED = mavutil.mavlink.MAV_FRAME_LOCAL_NED

# PX4 custom_mode 상위 바이트 = main mode 번호.
PX4_MAIN_MODE = {
    1: "MANUAL",
    2: "ALTCTL",
    3: "POSCTL",
    4: "AUTO",
    5: "ACRO",
    6: "OFFBOARD",
    7: "STABILIZED",
    8: "RATTITUDE",
    9: "SIMPLE",
    10: "TERMINATION",
}

# yaw 를 이 시간 넘게 못 받으면 "모른다"고 봅니다.
YAW_MAX_AGE = 2.0


def px4_mode_string(msg):
    """PX4 HEARTBEAT -> 모드 이름.

    pymavlink 버전에 따라 mode_string_v10() 의 PX4 처리가 다르므로
    custom_mode 를 직접 풀어서 버전에 흔들리지 않게 합니다.
    """
    if not msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED:
        return "MANUAL"
    main_mode = (msg.custom_mode >> 16) & 0xFF
    return PX4_MAIN_MODE.get(main_mode, f"MODE({main_mode})")


class MavlinkLink:
    def __init__(self, cfg):
        m = cfg["mavlink"]
        s = cfg["safety"]
        self.dry_run = s["dry_run"]
        self.require_offboard = s["require_offboard"]
        self.require_armed = s["require_armed"]

        print(f"[MAVLink] 연결 중: {m['connection']} ...")
        self.master = mavutil.mavlink_connection(m["connection"], baud=m["baud"])
        self.master.wait_heartbeat()
        print(f"[MAVLink] 연결됨 (system {self.master.target_system})")

        self._armed = False
        self._mode = ""
        self._yaw = None          # rad, 기수 방향 (ATTITUDE 에서 받음)
        self._yaw_at = 0.0
        self._last_heartbeat = 0.0

        self._request_attitude(m.get("attitude_rate", 10))

    # ---------- 초기 설정 ----------

    def _request_attitude(self, hz):
        """ATTITUDE 를 hz 로 보내달라고 요청합니다.

        PX4 는 REQUEST_DATA_STREAM(ArduPilot 방식)을 무시하므로
        MAV_CMD_SET_MESSAGE_INTERVAL 을 씁니다.
        """
        interval_us = int(1_000_000 / max(1, hz))
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
            0,
            mavutil.mavlink.MAVLINK_MSG_ID_ATTITUDE,
            interval_us,
            0, 0, 0, 0, 0,
        )

    # ---------- 상태 ----------

    def poll(self):
        """쌓인 메시지를 비우면서 모드/시동/기수 방향을 갱신합니다. 매 루프 호출."""
        while True:
            msg = self.master.recv_match(type=["HEARTBEAT", "ATTITUDE"], blocking=False)
            if msg is None:
                break
            if msg.get_type() == "HEARTBEAT":
                # 지상국이나 다른 기기의 하트비트는 무시합니다.
                if msg.get_srcSystem() != self.master.target_system:
                    continue
                self._armed = bool(
                    msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
                )
                self._mode = px4_mode_string(msg)
            else:
                self._yaw = msg.yaw
                self._yaw_at = time.monotonic()

        self._send_heartbeat()

    def _send_heartbeat(self):
        """1Hz 로 우리 쪽 하트비트를 보냅니다.

        PX4 는 이걸 받아야 동반 컴퓨터를 살아있는 링크 상대로 인식합니다.
        """
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

    @property
    def yaw_deg(self):
        return None if self._yaw is None else math.degrees(self._yaw)

    def _yaw_known(self):
        return (
            self._yaw is not None
            and time.monotonic() - self._yaw_at <= YAW_MAX_AGE
        )

    def ready_to_command(self):
        """지금 속도 명령을 보내도 되는 상태인지."""
        if self.require_armed and not self._armed:
            return False, "시동 대기중"
        if self.require_offboard and self._mode != "OFFBOARD":
            return False, f"OFFBOARD 아님 (현재 {self._mode or '?'})"
        if not self._yaw_known():
            # 기수 방향을 모르면 화면 기준 명령을 지구 기준으로 못 바꿉니다.
            return False, "ATTITUDE 대기중 (기수 방향 모름)"
        return True, "OK"

    # ---------- 명령 ----------

    def send_velocity(self, cmd):
        """Command(기체 기준) 를 지구 기준으로 돌려서 전송.

        OFFBOARD 진입 조건 때문에 모드/시동과 무관하게 매 루프 호출해야 합니다.
        보낼 게 없으면 cmd 를 Command() (정지) 로 주세요.
        """
        if self.dry_run:
            return
        if not self._yaw_known():
            return

        # 기체 기준(전/우) -> 지구 기준(북/동). yaw 는 북쪽 기준 시계방향.
        c = math.cos(self._yaw)
        s = math.sin(self._yaw)
        north = cmd.forward * c - cmd.right * s
        east = cmd.forward * s + cmd.right * c

        self.master.mav.set_position_target_local_ned_send(
            int(time.monotonic() * 1000) & 0xFFFFFFFF,  # time_boot_ms
            self.master.target_system,
            self.master.target_component,
            FRAME_LOCAL_NED,
            VELOCITY_YAWRATE_MASK,
            0, 0, 0,                                    # x, y, z (무시)
            north, east, cmd.down,                      # vx, vy, vz [m/s]
            0, 0, 0,                                    # afx, afy, afz (무시)
            0,                                          # yaw (무시)
            math.radians(cmd.yaw_rate),                 # yaw_rate [rad/s]
        )

    def send_stop(self):
        self.send_velocity(Command())

    def statustext(self, text):
        """지상국(QGroundControl 등) 화면에 메시지를 띄웁니다."""
        if self.dry_run:
            return
        self.master.mav.statustext_send(
            mavutil.mavlink.MAV_SEVERITY_INFO, text.encode()[:50]
        )
