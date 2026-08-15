#!/usr/bin/env python3
"""3단계 점검: 서보 드로퍼.

    python3 tools/check_dropper.py            # 키 입력으로 열기/닫기 테스트
    python3 tools/check_dropper.py --angle 45 # 특정 각도로 보내보기 (각도 찾기)

★ 프로펠러를 뺀 상태에서, 드론을 책상에 올려두고 하세요.
★ config.yaml 의 dropper.enable 이 false 여도 이 도구는 서보를 움직입니다.
  (지상 점검이 목적이므로)

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
    ap.add_argument("--angle", type=float, help="이 각도로 한 번 보내고 끝냅니다")
    args = ap.parse_args()

    cfg = load_config(os.path.join(ROOT, "config.yaml"))
    # 지상 점검이므로 설정과 무관하게 서보를 실제로 움직입니다.
    cfg["dropper"]["enable"] = True
    cfg["safety"]["dry_run"] = False

    d = cfg["dropper"]
    print("=" * 52)
    print(f"  GPIO       : {d['pin']}  (BCM 번호)")
    print(f"  닫힘/열림  : {d['closed_angle']}도 / {d['open_angle']}도")
    print(f"  펄스 폭    : {d['min_pulse_us']} ~ {d['max_pulse_us']} us")
    print("=" * 52)

    dropper = Dropper(cfg)
    if dropper.simulate:
        print("\n서보를 열지 못했습니다. 아래를 확인하세요:")
        print("  - gpiozero 설치됨?     sudo apt install python3-gpiozero python3-lgpio")
        print("  - 다른 프로그램이 같은 GPIO 를 쓰고 있지 않은지")
        return 1

    try:
        if args.angle is not None:
            print(f"\n{args.angle}도로 이동합니다...")
            dropper._move(args.angle)
            time.sleep(1.5)
            print("이 각도에서 물건이 걸리나요? 빠지나요?")
            print("-> config.yaml 의 closed_angle / open_angle 에 적으세요")
            return 0

        print("\n키를 눌러 서보를 제어하세요 (Enter 불필요).")
        print("  o: 열기   c: 닫기   q: 종료")
        while True:
            key = _read_key().lower()
            if key == "o":
                print("\n열기 (물건을 놓는 자세)")
                # drop()의 자동 닫힘/1회 제한 없이 자세를 직접 점검합니다.
                dropper._move(dropper.open_angle)
            elif key == "c":
                print("\n닫기 (물건을 잡는 자세)")
                dropper.close()
                _wait(dropper, 0.6)
            elif key == "q":
                print("\n종료")
                break

        print("떨림이 심하면: 5V 전원이 FC 서보 레일에서 오는지, 접지가 Pi 와 공통인지 확인")
        return 0
    except KeyboardInterrupt:
        print("\n중단")
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
        raise RuntimeError("키 입력 테스트는 터미널에서 실행해야 합니다")

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


if __name__ == "__main__":
    sys.exit(main())
