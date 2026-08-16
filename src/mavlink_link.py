"""pymavlink로 ArduCopter와 통신하고 AltHold RC override를 관리합니다.

프로그램은 스스로 시동하거나 비행 모드를 바꾸지 않습니다. 시동 상태에서 CH8을
HIGH로 올리고 네 개의 주 조종 스틱을 중립에 두면 OBC가 RC1~RC4를 대신
입력합니다. 시동이 풀리거나 CH8을 LOW로 내리면 override를 해제합니다.

override 활성 중에는 RC1~RC4 실제 스틱 입력을 사용하지 않습니다. 제어권 회수는
override하지 않는 CH8 허용 스위치를 LOW로 내려 수행합니다.
"""

import time

from pymavlink import mavutil


RC_RELEASE = 0
RC_IGNORE = 0xFFFF
RC_CHANNELS_MSG_ID = 65

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


def _clamp(value, low, high):
    return max(low, min(high, value))


class MavlinkLink:
    def __init__(self, cfg):
        m = cfg["mavlink"]
        s = cfg["safety"]
        rc = m.get("rc_override", {})
        self.require_armed = s["require_armed"]
        self.rc_timeout = float(rc.get("input_timeout", 0.5))
        self.neutral_deadband = int(rc.get("neutral_deadband", 50))
        self.neutral_hold = float(rc.get("neutral_hold", 0.5))
        self.pwm_span = int(rc.get("pwm_span", 100))
        self.pwm_min = int(rc.get("pwm_min", 1100))
        self.pwm_max = int(rc.get("pwm_max", 1900))
        self.enable_channel = int(rc.get("enable_channel", 8))
        self.enable_pwm_min = int(rc.get("enable_pwm_min", 1800))

        self.channels = {
            "roll": int(rc.get("roll_channel", 1)),
            "pitch": int(rc.get("pitch_channel", 2)),
            "throttle": int(rc.get("throttle_channel", 3)),
            "yaw": int(rc.get("yaw_channel", 4)),
        }
        self.trims = {
            axis: int(rc.get(f"{axis}_trim", 1500)) for axis in self.channels
        }
        self.signs = {
            "roll": int(rc.get("roll_sign", 1)),
            "pitch": int(rc.get("pitch_sign", -1)),
            "throttle": int(rc.get("throttle_sign", -1)),
            "yaw": int(rc.get("yaw_sign", 1)),
        }
        self.pwm_per_unit = {
            "roll": float(rc.get("roll_pwm_per_unit", 250.0)),
            "pitch": float(rc.get("pitch_pwm_per_unit", 250.0)),
            "throttle": float(rc.get("throttle_pwm_per_unit", 400.0)),
            "yaw": float(rc.get("yaw_pwm_per_unit", 3.0)),
        }

        if len(set(self.channels.values())) != 4:
            raise ValueError("rc_override primary channels must be different")
        if any(channel < 1 or channel > 8 for channel in self.channels.values()):
            raise ValueError("rc_override primary channels must be in RC1..RC8")
        if self.enable_channel < 1 or self.enable_channel > 18:
            raise ValueError("rc_override enable_channel must be in RC1..RC18")
        if self.enable_channel in self.channels.values():
            raise ValueError("rc_override enable_channel must not be a primary channel")
        if any(sign not in (-1, 1) for sign in self.signs.values()):
            raise ValueError("rc_override axis signs must be -1 or 1")

        # ArduPilot은 MAV_GCS_SYSID와 일치하는 송신자에게서만 RC override를 받습니다.
        source_system = m.get("source_system", 255)
        source_component = m.get("source_component", 191)

        print(f"[MAVLink] connecting: {m['connection']} ...")
        self.master = mavutil.mavlink_connection(
            m["connection"],
            baud=m["baud"],
            source_system=source_system,
            source_component=source_component,
        )
        self.master.wait_heartbeat()
        print(
            f"[MAVLink] connected (FC {self.master.target_system}/"
            f"{self.master.target_component}, OBC {source_system}/{source_component})"
        )

        self._armed = False
        self._mode = ""
        self._last_heartbeat = 0.0
        self._rc_values = {}
        self._last_rc = 0.0
        self._neutral_since = None
        self._override_active = False

        # RC_CHANNELS를 10Hz로 요청합니다. 설정은 FC에 저장되지 않습니다.
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
            0,
            RC_CHANNELS_MSG_ID,
            100_000,
            0, 0, 0, 0, 0,
        )

    # ---------- 상태 ----------

    def poll(self):
        """수신 버퍼를 비우면서 FC, RC, override 상태를 갱신합니다."""
        while True:
            msg = self.master.recv_match(blocking=False)
            if msg is None:
                break
            if msg.get_srcSystem() != self.master.target_system:
                continue

            msg_type = msg.get_type()
            if msg_type == "HEARTBEAT":
                if msg.autopilot != mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA:
                    continue
                self._armed = bool(
                    msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
                )
                self._mode = arducopter_mode_string(msg)
            elif msg_type == "RC_CHANNELS":
                count = min(int(msg.chancount), 18)
                self._rc_values = {
                    channel: getattr(msg, f"chan{channel}_raw")
                    for channel in range(1, count + 1)
                }
                self._last_rc = time.monotonic()

        if not self._armed:
            self._override_active = False
            self._neutral_since = None

        self._send_heartbeat()

    def _send_heartbeat(self):
        """ArduCopter가 컴패니언 링크를 감시할 수 있도록 1Hz heartbeat 전송."""
        now = time.monotonic()
        if now - self._last_heartbeat < 1.0:
            return
        self._last_heartbeat = now
        self.master.mav.heartbeat_send(
            mavutil.mavlink.MAV_TYPE_ONBOARD_CONTROLLER,
            mavutil.mavlink.MAV_AUTOPILOT_INVALID,
            0, 0, mavutil.mavlink.MAV_STATE_ACTIVE,
        )

    @property
    def armed(self):
        return self._armed

    @property
    def mode(self):
        return self._mode

    @property
    def override_active(self):
        return self._override_active

    def ready_to_command(self):
        """시동 상태에서 OBC가 조종기를 대신 입력해도 되는지 반환합니다."""
        if self.require_armed and not self._armed:
            self._neutral_since = None
            return False, "WAIT_ARM"
        if time.monotonic() - self._last_rc > self.rc_timeout:
            self._neutral_since = None
            return False, "RC_INPUT_STALE"
        if self._rc_values.get(self.enable_channel, 0) < self.enable_pwm_min:
            self._neutral_since = None
            return False, "RC_OVERRIDE_DISABLED"
        if self._override_active:
            return True, "RC_OVERRIDE"
        if not self._sticks_neutral():
            self._neutral_since = None
            return False, "PILOT_INPUT"

        now = time.monotonic()
        if self._neutral_since is None:
            self._neutral_since = now
        if now - self._neutral_since < self.neutral_hold:
            return False, "WAIT_NEUTRAL"
        return True, "RC_OVERRIDE_READY"

    def ready_to_release(self):
        """시동·비행 모드와 무관하게 CH8 투하 허용 상태를 반환합니다."""
        if time.monotonic() - self._last_rc > self.rc_timeout:
            return False, "RC_INPUT_STALE"
        if self._rc_values.get(self.enable_channel, 0) < self.enable_pwm_min:
            return False, "RELEASE_DISABLED"
        return True, "RELEASE_ENABLED"

    def _sticks_neutral(self):
        return all(
            abs(self._rc_values.get(channel, 0) - self.trims[axis])
            <= self.neutral_deadband
            for axis, channel in self.channels.items()
        )

    # ---------- 명령 ----------

    def command_to_pwm(self, cmd):
        """Controller의 축 명령을 보수적인 RC PWM 편차로 변환합니다."""
        values = {
            "roll": cmd.right,
            "pitch": cmd.forward,
            "throttle": cmd.down,
            "yaw": cmd.yaw_rate,
        }
        result = {}
        for axis, value in values.items():
            offset = _clamp(
                value * self.pwm_per_unit[axis], -self.pwm_span, self.pwm_span
            )
            pwm = self.trims[axis] + self.signs[axis] * offset
            result[self.channels[axis]] = int(
                round(_clamp(pwm, self.pwm_min, self.pwm_max))
            )
        return result

    def send_override(self, cmd):
        """RC1~RC8 중 설정된 주 조종 채널만 override합니다."""
        channels = [RC_IGNORE] * 18
        for channel, pwm in self.command_to_pwm(cmd).items():
            channels[channel - 1] = pwm
        self.master.mav.rc_channels_override_send(
            self.master.target_system,
            self.master.target_component,
            *channels,
        )
        self._override_active = True

    def release_override(self):
        """OBC가 잡은 주 조종 채널을 실제 수신기 입력으로 되돌립니다."""
        channels = [RC_IGNORE] * 18
        for channel in self.channels.values():
            channels[channel - 1] = RC_RELEASE
        self.master.mav.rc_channels_override_send(
            self.master.target_system,
            self.master.target_component,
            *channels,
        )
        self._override_active = False

    def statustext(self, text):
        """지상국(Mission Planner 등) 화면에 메시지를 띄웁니다."""
        self.master.mav.statustext_send(
            mavutil.mavlink.MAV_SEVERITY_INFO, text.encode()[:50]
        )
