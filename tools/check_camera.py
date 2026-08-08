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


def main():
    cfg = load_config(os.path.join(ROOT, "config.yaml"))
    print(f"모델: {cfg['camera']['model']}")
    print("펌웨어를 카메라에 올리는 중입니다. 처음에는 1~2분 걸릴 수 있습니다...\n")

    det = Detector(cfg)
    print(f"해상도: {det.frame_size}, 라벨 {len(det.labels)}개")
    print(f"찾는 대상: '{cfg['detection']['target_class']}'\n")

    if cfg["detection"]["target_class"] not in det.labels:
        print("!! 경고: target_class 가 라벨 파일에 없습니다. 사용 가능한 라벨 일부:")
        print("   " + ", ".join(det.labels[:20]))
        print()

    print("실측 fps 가 설정값(%d)에 가까운지 확인하세요.\n" % cfg["camera"]["fps"])

    last = 0.0
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

            if now - last > 0.5:
                if results:
                    counts = Counter(d.label for d in results)
                    summary = ", ".join(f"{k}x{v}" for k, v in counts.items())
                    best = max(results, key=lambda d: d.conf)
                    detail = f"최고: {best.label} {best.conf:.2f} box={best.box}"
                else:
                    summary, detail = "검출 없음", ""
                print(f"[{fps:4.1f} fps] {summary:34s} | {detail}")
                last = now
    except KeyboardInterrupt:
        print("\n종료")
    finally:
        det.close()


if __name__ == "__main__":
    main()
