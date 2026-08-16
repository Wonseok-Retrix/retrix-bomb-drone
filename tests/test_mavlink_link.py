import os
import sys
import types
import unittest
from unittest.mock import patch


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

# 개발 PC에 pymavlink가 없어도 순수 변환/상태 로직은 검증할 수 있습니다.
try:
    import pymavlink  # noqa: F401
except ModuleNotFoundError:
    mavlink = types.SimpleNamespace(
        MAV_AUTOPILOT_ARDUPILOTMEGA=3,
        MAV_MODE_FLAG_CUSTOM_MODE_ENABLED=1,
        MAV_MODE_FLAG_SAFETY_ARMED=128,
    )
    mavutil = types.SimpleNamespace(mavlink=mavlink)
    sys.modules["pymavlink"] = types.SimpleNamespace(mavutil=mavutil)
    sys.modules["pymavlink.mavutil"] = mavutil

from command import Command
from mavlink_link import MavlinkLink


def make_link():
    link = MavlinkLink.__new__(MavlinkLink)
    link.require_armed = True
    link.rc_timeout = 0.5
    link.neutral_deadband = 50
    link.neutral_hold = 0.5
    link.pwm_span = 100
    link.pwm_min = 1100
    link.pwm_max = 1900
    link.enable_channel = 8
    link.enable_pwm_min = 1800
    link.channels = {"roll": 1, "pitch": 2, "throttle": 3, "yaw": 4}
    link.trims = {axis: 1500 for axis in link.channels}
    link.signs = {"roll": 1, "pitch": -1, "throttle": -1, "yaw": 1}
    link.pwm_per_unit = {
        "roll": 250.0,
        "pitch": 250.0,
        "throttle": 400.0,
        "yaw": 10.0 / 3.0,
    }
    link._armed = True
    link._mode = "ALT_HOLD"
    link._rc_values = {1: 1500, 2: 1500, 3: 1500, 4: 1500, 8: 1900}
    link._last_rc = 10.0
    link._neutral_since = None
    link._override_active = False
    return link


class FakeMav:
    def __init__(self):
        self.override_calls = []

    def rc_channels_override_send(self, *args):
        self.override_calls.append(args)


class ReadyToCommandTests(unittest.TestCase):
    @patch("mavlink_link.time.monotonic", return_value=10.0)
    def test_requires_neutral_hold_before_first_override(self, monotonic):
        link = make_link()

        self.assertEqual(link.ready_to_command(), (False, "WAIT_NEUTRAL"))
        monotonic.return_value = 10.5
        self.assertEqual(link.ready_to_command(), (True, "RC_OVERRIDE_READY"))

    @patch("mavlink_link.time.monotonic", return_value=10.0)
    def test_pilot_input_blocks_initial_override(self, _):
        link = make_link()
        link._rc_values[1] = 1600

        self.assertEqual(link.ready_to_command(), (False, "PILOT_INPUT"))

    @patch("mavlink_link.time.monotonic", return_value=10.5)
    def test_flight_mode_does_not_block_override(self, _):
        link = make_link()
        link._mode = "STABILIZE"
        link._neutral_since = 10.0

        self.assertEqual(link.ready_to_command(), (True, "RC_OVERRIDE_READY"))

    @patch("mavlink_link.time.monotonic", return_value=10.0)
    def test_active_override_does_not_treat_its_own_pwm_as_pilot_input(self, _):
        link = make_link()
        link._override_active = True
        link._rc_values.update({1: 1600, 2: 1400, 3: 1450})

        self.assertEqual(link.ready_to_command(), (True, "RC_OVERRIDE"))

    @patch("mavlink_link.time.monotonic", return_value=10.0)
    def test_enable_switch_low_disables_active_override(self, _):
        link = make_link()
        link._override_active = True
        link._rc_values[8] = 1100

        self.assertEqual(link.ready_to_command(), (False, "RC_OVERRIDE_DISABLED"))


class ReadyToReleaseTests(unittest.TestCase):
    @patch("mavlink_link.time.monotonic", return_value=10.0)
    def test_ch8_enables_release_while_disarmed_and_outside_althold(self, _):
        link = make_link()
        link._armed = False
        link._mode = "STABILIZE"

        self.assertEqual(link.ready_to_release(), (True, "RELEASE_ENABLED"))

    @patch("mavlink_link.time.monotonic", return_value=10.0)
    def test_ch8_low_disables_release(self, _):
        link = make_link()
        link._rc_values[8] = 1100

        self.assertEqual(link.ready_to_release(), (False, "RELEASE_DISABLED"))

    @patch("mavlink_link.time.monotonic", return_value=11.0)
    def test_stale_rc_input_disables_release(self, _):
        link = make_link()

        self.assertEqual(link.ready_to_release(), (False, "RC_INPUT_STALE"))


class PwmConversionTests(unittest.TestCase):
    def test_maps_body_commands_to_default_copter_stick_directions(self):
        link = make_link()

        pwm = link.command_to_pwm(
            Command(forward=0.4, right=0.2, down=0.25, yaw_rate=-15)
        )

        self.assertEqual(pwm, {1: 1550, 2: 1400, 3: 1400, 4: 1450})

    def test_pwm_span_limits_large_command(self):
        link = make_link()

        self.assertEqual(link.command_to_pwm(Command(down=10.0))[3], 1400)

    def test_altitude_commands_map_to_althold_throttle(self):
        link = make_link()

        self.assertEqual(link.command_to_pwm(Command())[3], 1500)
        self.assertEqual(link.command_to_pwm(Command(down=0.1))[3], 1460)
        self.assertEqual(link.command_to_pwm(Command(down=-0.1))[3], 1540)

    def test_override_leaves_channel_8_under_receiver_control(self):
        link = make_link()
        mav = FakeMav()
        link.master = types.SimpleNamespace(
            target_system=1, target_component=1, mav=mav
        )

        link.send_override(Command(right=0.4))
        sent = mav.override_calls[-1][2:]

        self.assertEqual(sent[:4], (1600, 1500, 1500, 1500))
        self.assertEqual(sent[7], 0xFFFF)

    def test_release_only_releases_primary_channels(self):
        link = make_link()
        mav = FakeMav()
        link.master = types.SimpleNamespace(
            target_system=1, target_component=1, mav=mav
        )

        link.release_override()
        sent = mav.override_calls[-1][2:]

        self.assertEqual(sent[:4], (0, 0, 0, 0))
        self.assertTrue(all(value == 0xFFFF for value in sent[4:]))


if __name__ == "__main__":
    unittest.main()
