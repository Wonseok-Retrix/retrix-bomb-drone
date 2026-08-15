#!/usr/bin/env python3
"""Object Tracking Drone - 메인 스크립트.

    python3 src/track_and_follow.py                # config.yaml 사용
    python3 src/track_and_follow.py --config my.yaml
    python3 src/track_and_follow.py --live         # 실제 명령 전송

구조:
    [카메라 스레드]  검출 --> 추적 --> 목표 저장        (camera.fps 속도, 1~2 fps)
    [메인 루프]      목표 --> P제어 --> MAVLink 전송    (mavlink.send_rate 속도, 10Hz)

두 개를 분리한 이유:
  ArduCopter GUIDED 속도 명령은 GUID_TIMEOUT(기본 3초) 동안 끊기면 기체가 정지합니다.
  카메라가 1~2 fps 로 느려도 명령 스트림은 10Hz 로 일정하게 유지되어야 합니다.

카메라가 느린 것에 대한 대응:
  프레임 사이(최대 1초)에는 볼 수 있는 게 없습니다. 그 시간 동안 같은 속도로
  계속 밀면 목표를 지나칩니다. 그래서 목표에 붙은 나이(age)를 제어기에 넘겨
  명령의 세기를 점점 줄입니다. 자세한 내용은 controller.py 위쪽 주석 참고.
"""

import argparse
import os
import sys
import threading
import time

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from command import Command
from controller import Controller
from detector import Detector
from dropper import Dropper
from mavlink_link import MavlinkLink
from release import ReleaseJudge
from tracker import Tracker

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config(path):
    with open(path) as f:
        cfg = yaml.safe_load(f)
    # 상대경로는 프로젝트 루트 기준으로 해석
    for key in ("model", "labels"):
        p = cfg["camera"][key]
        if not os.path.isabs(p):
            cfg["camera"][key] = os.path.join(ROOT, p)
    return cfg


class VisionThread:
    """카메라에서 목표를 계속 갱신하는 백그라운드 스레드."""

    def __init__(self, detector, tracker):
        self.detector = detector
        self.tracker = tracker
        self._lock = threading.Lock()
        self._target = None
        self._n_det = 0
        self._updated_at = 0.0
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        self._thread.start()

    def _loop(self):
        while self._running:
            try:
                detections = self.detector.read()
                target = self.tracker.update(detections)
            except Exception as e:  # 카메라 오류로 드론이 폭주하면 안 됨
                print(f"[CAMERA ERROR] {e}")
                time.sleep(0.5)
                continue
            with self._lock:
                self._target = target
                self._n_det = len(detections)
                self._updated_at = time.monotonic()

    def latest(self, stall_timeout):
        """(목표, 검출 개수, 카메라 멈춤 여부) 를 돌려줍니다.

        목표가 얼마나 오래된 정보인지는 target.age 에 들어있고, 그걸로 명령 세기를
        줄이는 건 제어기가 합니다. 여기서 보는 건 '카메라 자체가 죽었는가' 뿐입니다.
        """
        with self._lock:
            target, n_det, updated_at = self._target, self._n_det, self._updated_at
        if updated_at == 0.0 or time.monotonic() - updated_at > stall_timeout:
            return None, n_det, True   # 카메라가 프레임을 아예 못 주고 있음
        return target, n_det, False

    def stop(self):
        self._running = False
        self._thread.join(timeout=2.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(ROOT, "config.yaml"))
    ap.add_argument("--live", action="store_true", help="send commands to the drone")
    ap.add_argument("--no-mavlink", action="store_true", help="test the camera only")
    args = ap.parse_args()

    cfg = load_config(args.config)

    print("=" * 60)
    print(f"  Target class : {cfg['detection']['target_class']}")
    print(f"  Model        : {os.path.basename(cfg['camera']['model'])}")
    print(f"  Camera       : {cfg['camera']['fps']} fps / {cfg['camera'].get('rotation', 0)} deg")
    print(f"  Command rate : {cfg['mavlink']['send_rate']} Hz")
    print(f"  Dropper      : {'active' if args.live else 'simulation'}")
    print(f"  Mode         : {'*** LIVE ***' if args.live else 'DRY RUN (no commands sent)'}")
    print("=" * 60)

    detector = Detector(cfg)
    tracker = Tracker(cfg, detector.frame_size)
    controller = Controller(cfg["control"])
    dropper = Dropper(cfg, live=args.live)
    judge = ReleaseJudge(cfg)
    link = None if args.no_mavlink else MavlinkLink(cfg, live=args.live)

    vision = VisionThread(detector, tracker)
    vision.start()

    period = 1.0 / cfg["mavlink"]["send_rate"]
    # 카메라가 이 시간 넘게 프레임을 아예 못 주면 "죽었다"고 보고 정지합니다.
    # 목표가 조금 오래된 것과는 다른 이야기입니다 (그건 controller 가 감쇠로 처리).
    stall_timeout = cfg["camera"]["stall_timeout"]
    status_interval = max(1.0, float(cfg["mavlink"].get("status_interval", 5.0)))

    last_log = 0.0
    last_status = 0.0
    was_ready = False

    try:
        while True:
            loop_start = time.monotonic()

            target, n_det, stalled = vision.latest(stall_timeout)
            age = target.age if target is not None else float("inf")
            cmd = controller.compute(target, age)

            if link is not None:
                link.poll()
                ready, reason = link.ready_to_command()
                if ready and not was_ready:
                    link.statustext("TRACKING: guided control ON")
                was_ready = ready

                if not ready:
                    cmd = Command()

                # 목표가 없어도 GUIDED 상태에서는 '정지' 명령을 계속 보냅니다.
                # 통신이 끊기면 ArduCopter의 GUID_TIMEOUT 안전 동작이 정지시킵니다.
                link.send_velocity(cmd)

                now = time.monotonic()
                if now - last_status >= status_interval:
                    link.statustext(
                        _tracking_status(target, n_det, stalled, ready, link)
                    )
                    last_status = now
            else:
                ready, reason = False, "MAVLINK_DISABLED"

            # 과녁 위에 잘 정렬됐으면 투하합니다. 판단은 release.py 가 합니다.
            if judge.update(target, ready) and dropper.drop():
                if link is not None:
                    link.statustext("DROP")
            dropper.update()   # 열어둔 시간이 지나면 스스로 닫힙니다

            now = time.monotonic()
            if now - last_log > 0.5:
                _log(target, cmd, reason, n_det, stalled, controller)
                print(f"     dropper: {judge.reason}"
                      f"{' | RELEASED' if dropper.dropped else ''}")
                last_log = now

            time.sleep(max(0.0, period - (time.monotonic() - loop_start)))

    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        vision.stop()
        if link is not None:
            link.send_stop()
        dropper.stop()
        detector.close()


def _log(target, cmd, reason, n_det, stalled, controller):
    if stalled:
        print(f"[!!] CAMERA STALL (no frames) -> stop command | {reason}")
    elif target is None:
        print(f"[--] NO TARGET ({n_det} detections) | {reason}")
    else:
        age = target.age
        print(
            f"[OK] x={target.offset_x:+.2f} y={target.offset_y:+.2f} "
            f"size={target.size:.2f} conf={target.conf:.2f} "
            f"age={age:.2f}s x{controller.freshness(age):.2f} "
            f"-> fwd={cmd.forward:+.2f} right={cmd.right:+.2f} down={cmd.down:+.2f}m/s "
            f"yaw={cmd.yaw_rate:+.1f}deg/s | {reason}"
        )


def _tracking_status(target, n_det, stalled, ready, link):
    """GCS에 보낼 50바이트 이하의 ASCII 추적 상태."""
    if ready:
        state = "ACTIVE"
    elif not link.armed:
        state = "WAIT_ARM"
    else:
        state = f"WAIT_{link.mode or 'MODE'}"

    if stalled:
        tracking = "CAM_STALL"
    elif target is None:
        tracking = f"NO_TARGET({n_det})"
    else:
        tracking = f"LOCK({target.offset_x:+.2f},{target.offset_y:+.2f})"

    return f"OBC TRACK {state} {tracking}"[:50]


if __name__ == "__main__":
    main()
