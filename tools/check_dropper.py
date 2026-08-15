#!/usr/bin/env python3
"""3단계 점검: 서보 드로퍼.

    python3 tools/check_dropper.py            # 키 입력으로 열기/닫기 테스트
    python3 tools/check_dropper.py --angle 45 # 특정 각도로 보내보기 (각도 찾기)

★ 프로펠러를 뺀 상태에서, 드론을 책상에 올려두고 하세요.
★ 이 도구는 지상 점검이 목적이므로 서보를 실제로 움직입니다.

각도 찾는 법:
  1) --angle 로 0, 30, 60, 90 을 넣어보며 물건이 걸리는 각도와 빠지는 각도를 찾습니다
  2) 그 두 값을 config.yaml 의 closed_angle / open_angle 에 적습니다
"""

import argparse
import os
import sys
import termios
import time
import tty

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from track_and_follow import load_config  # noqa: E402
from dropper import Dropper  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--angle", type=float, help="move to this angle once, then exit")
    args = ap.parse_args()

    cfg = load_config(os.path.join(ROOT, "config.yaml"))

    d = cfg["dropper"]
    print("=" * 52)
    print(f"  GPIO        : {d['pin']}  (BCM numbering)")
    print(f"  Closed/Open : {d['closed_angle']} deg / {d['open_angle']} deg")
    print(f"  Pulse width : {d['min_pulse_us']} ~ {d['max_pulse_us']} us")
    print("=" * 52)

    dropper = Dropper(cfg, live=True)
    if dropper.simulate:
        print("\nCould not initialize the servo. Check:")
        print("  - gpiozero installed?  sudo apt install python3-gpiozero python3-lgpio")
        print("  - no other process is using the same GPIO")
        return 1

    try:
        if args.angle is not None:
            print(f"\nMoving to {args.angle} degrees...")
            dropper._move(args.angle)
            time.sleep(1.5)
            print("Does this angle hold or release the payload?")
            print("-> Set closed_angle / open_angle in config.yaml")
            return 0

        print("\nPress a key to control the servo (no Enter required).")
        print("  o: open   c: close   q: quit")
        while True:
            key = _read_key().lower()
            if key == "o":
                print("\nOpen (release position)")
                # drop()의 자동 닫힘/1회 제한 없이 자세를 직접 점검합니다.
                dropper._move(dropper.open_angle)
            elif key == "c":
                print("\nClose (holding position)")
                dropper.close()
                _wait(dropper, 0.6)
            elif key == "q":
                print("\nQuit")
                break

        print("If the servo jitters, check the 5V servo-rail supply and shared ground with the Pi.")
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted")
        return 1
    finally:
        dropper.close()
        time.sleep(0.6)
        dropper.stop()


def _wait(dropper, seconds):
    """기다리는 동안에도 dropper 의 자동 닫힘 타이머를 돌려줍니다."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        dropper.update()
        time.sleep(0.05)


def _read_key():
    """터미널에서 Enter 없이 키 하나를 읽고 설정을 즉시 복원합니다."""
    if not sys.stdin.isatty():
        raise RuntimeError("interactive key testing requires a terminal")

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


if __name__ == "__main__":
    sys.exit(main())
