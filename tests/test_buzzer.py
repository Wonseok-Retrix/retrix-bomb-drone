import os
import sys
import threading
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from buzzer import StatusBuzzer


def make_buzzer():
    buzzer = StatusBuzzer.__new__(StatusBuzzer)
    buzzer.enabled = True
    buzzer._condition = threading.Condition()
    buzzer._generation = 0
    buzzer._pattern = ()
    buzzer._continuous = False
    return buzzer


class StatusBuzzerTests(unittest.TestCase):
    def test_release_waiting_stays_continuous_without_restarting(self):
        buzzer = make_buzzer()

        buzzer.notify_cycle(tracking=True, release_waiting=True)
        generation = buzzer._generation
        buzzer.notify_cycle(tracking=None, release_waiting=True)

        self.assertTrue(buzzer._continuous)
        self.assertEqual(buzzer._generation, generation)

    def test_release_waiting_stops_without_a_new_camera_frame(self):
        buzzer = make_buzzer()
        buzzer.notify_cycle(tracking=True, release_waiting=True)

        buzzer.notify_cycle(tracking=None, release_waiting=False)

        self.assertFalse(buzzer._continuous)
        self.assertEqual(buzzer._pattern, ())


if __name__ == "__main__":
    unittest.main()
