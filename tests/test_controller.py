import os
import sys
import unittest
from types import SimpleNamespace


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from controller import Controller


def make_controller(**overrides):
    config = {
        "lateral_gain": 1.0,
        "forward_gain": 1.0,
        "vertical_gain": 1.0,
        "deadband": 0.08,
        "target_size": 0.35,
        "size_deadband": 0.05,
        "stale_hold": 0.3,
        "stale_stop": 1.2,
    }
    config.update(overrides)
    return Controller(config)


class GainTests(unittest.TestCase):
    def test_gain_one_reaches_full_stick_at_maximum_position_error(self):
        controller = make_controller()
        target = SimpleNamespace(offset_x=1.0, offset_y=-1.0, size=0.35)

        command = controller.compute(target)

        self.assertEqual(command.right, 1.0)
        self.assertEqual(command.forward, 1.0)

    def test_gain_scales_normalized_position_error(self):
        controller = make_controller(lateral_gain=0.25, forward_gain=0.4)
        target = SimpleNamespace(offset_x=1.0, offset_y=-1.0, size=0.35)

        command = controller.compute(target)

        self.assertEqual(command.right, 0.25)
        self.assertEqual(command.forward, 0.4)

    def test_vertical_gain_reaches_endpoints_at_maximum_size_errors(self):
        controller = make_controller()

        descend = controller.compute(
            SimpleNamespace(offset_x=0.0, offset_y=0.0, size=0.0)
        )
        climb = controller.compute(
            SimpleNamespace(offset_x=0.0, offset_y=0.0, size=1.0)
        )

        self.assertEqual(descend.down, 1.0)
        self.assertEqual(climb.down, -1.0)


if __name__ == "__main__":
    unittest.main()
