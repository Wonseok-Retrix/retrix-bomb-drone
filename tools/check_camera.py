#!/usr/bin/env python3
"""1단계 점검: AI 카메라와 모델이 제대로 동작하는지만 확인합니다.

    python3 tools/check_camera.py

무엇이 몇 개 보이는지 콘솔에 계속 출력합니다. Ctrl+C 로 종료.
드론/MAVLink 는 전혀 사용하지 않습니다.
"""

import os
import sys
import time
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from track_and_follow import load_config  # noqa: E402
from detector import Detector  # noqa: E402
from tracker import resolve_target_classes  # noqa: E402


def main():
    cfg = load_config(os.path.join(ROOT, "config.yaml"))
    print(f"Model: {cfg['camera']['model']}")
    print(f"Rotation: {cfg['camera'].get('rotation', 0)} deg")
    print("Uploading firmware to the camera. The first run may take 1-2 minutes...\n")

    det = Detector(cfg)
    targets = resolve_target_classes(cfg)
    print(f"Resolution: {det.frame_size}, labels: {len(det.labels)}")
    print(f"Target classes: {targets}\n")

    missing = [c for c in targets if c not in det.labels]
    if missing:
        print("!! WARNING: target_classes not in the label file. Available labels include:")
        print("   " + ", ".join(det.labels[:20]))
        print()

    print("Check that measured fps is close to the configured value (%d).\n" % cfg["camera"]["fps"])

    frames = 0
    fps_t0 = time.monotonic()
    fps = 0.0
    try:
        while True:
            results = det.read()
            frames += 1
            now = time.monotonic()

            if now - fps_t0 >= 2.0:
                fps = frames / (now - fps_t0)
                frames, fps_t0 = 0, now

            if results:
                counts = Counter(d.label for d in results)
                summary = ", ".join(f"{k}x{v}" for k, v in counts.items())
                best = max(results, key=lambda d: d.conf)
                detail = f"best: {best.label} {best.conf:.2f} box={best.box}"
            else:
                summary, detail = "no detections", ""
            print(f"[{fps:4.1f} fps] {summary:34s} | {detail}")
    except KeyboardInterrupt:
        print("\nStopped")
    finally:
        det.close()


if __name__ == "__main__":
    main()
