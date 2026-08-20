import os
import sys
import unittest
from types import SimpleNamespace


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from tracker import Tracker, resolve_target_classes


def make_tracker(detection=None, **tracking_overrides):
    if detection is None:
        detection = {"target_classes": ["drone", "dssadasd"]}
    tracking = {
        "smoothing": 1.0,
        "lost_timeout": 1.0,
        "select": "largest",
    }
    tracking.update(tracking_overrides)
    cfg = {"detection": detection, "tracking": tracking}
    return Tracker(cfg, (640, 480))


def det(label, conf=0.9, box=(100, 100, 50, 50)):
    return SimpleNamespace(label=label, conf=conf, box=box)


class ResolveTargetClassesTests(unittest.TestCase):
    def test_prefers_target_classes_list(self):
        cfg = {"detection": {"target_classes": ["drone", "dssadasd"]}}
        self.assertEqual(resolve_target_classes(cfg), ["drone", "dssadasd"])

    def test_falls_back_to_single_target_class(self):
        cfg = {"detection": {"target_class": "drone"}}
        self.assertEqual(resolve_target_classes(cfg), ["drone"])


class MultiClassTrackingTests(unittest.TestCase):
    def test_tracks_each_configured_class(self):
        tracker = make_tracker()
        for label in ("drone", "dssadasd"):
            target = tracker.update([det(label)])
            self.assertIsNotNone(target)

    def test_ignores_non_target_class(self):
        tracker = make_tracker()
        target = tracker.update([det("person")])
        self.assertIsNone(target)


if __name__ == "__main__":
    unittest.main()
