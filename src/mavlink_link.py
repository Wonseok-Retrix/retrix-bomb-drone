"""pymavlink 로 비행 컨트롤러(MicoAir 743 v2 / ArduPilot)와 통신하는 모듈.

이 예제는 절대 스스로 시동을 걸거나 이륙하지 않습니다.
  1. 조종자가 조종기로 시동 + 이륙 (Loiter 등)
  2. 조종자가 GUIDED 모드로 전환
  3. 그때부터 이 스크립트가 속도 명령을 보냄
  4. 조종기로 모드를 빼면 즉시 조종자에게 제어권이 돌아감  <- 항상 가능
"""

import time

from pymavlink import mavutil

from command import Command

# SET_POSITION_TARGET_LOCAL_NED 에서 "속도 + yaw_rate 만 쓴다"는 뜻의 비트마스크.
# 위치/가속도/yaw 각도 비트를 전부 무시(1)로 켠 값입니다.
VELOCITY_YAWRATE_MASK = 0b0000010111000111

# 기체 기준 좌표계 (기수 방향이 +X). 화면 기준 제어와 궁합이 좋음.
FRAME_BODY_NED = mavutil.mavlink.MAV_FRAME_BODY_NED


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

    # ---------- 상태 ----------

    def poll(self):
        """쌓인 메시지를 비우면서 모드/시동 상태를 갱신합니다. 매 루프 호출."""
        while True:
            msg = self.master.recv_match(type="HEARTBEAT", blocking=False)
            if msg is None:
                break
            self._armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            self._mode = mavutil.mode_string_v10(msg)

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
        """Command 객체를 SET_POSITION_TARGET_LOCAL_NED 로 전송."""
        if self.dry_run:
            return
        self.master.mav.set_position_target_local_ned_send(
            int(time.monotonic() * 1000) & 0xFFFFFFFF,  # time_boot_ms
            self.master.target_system,
            self.master.target_component,
            FRAME_BODY_NED,
            VELOCITY_YAWRATE_MASK,
            0, 0, 0,                                    # x, y, z (무시)
            cmd.forward, cmd.right, cmd.down,           # vx, vy, vz [m/s]
            0, 0, 0,                                    # afx, afy, afz (무시)
            0,                                          # yaw (무시)
            _deg2rad(cmd.yaw_rate),                     # yaw_rate [rad/s]
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


def _deg2rad(deg):
    return deg * 0.017453292519943295
