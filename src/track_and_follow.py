#!/usr/bin/env python3
"""Object Tracking Drone - 메인 스크립트.

    python3 src/track_and_follow.py                # config.yaml 사용
    python3 src/track_and_follow.py --config my.yaml
    python3 src/track_and_follow.py --live         # dry_run 해제 (실제 명령 전송)

구조:
    [카메라 스레드]  검출 --> 추적 --> 목표 저장        (camera.fps 속도)
    [메인 루프]      목표 --> P제어 --> MAVLink 전송    (mavlink.send_rate 속도)

두 개를 분리한 이유:
  ArduPilot 은 GUIDED 명령이 3초 이상 끊기면 스스로 멈춥니다.
  카메라가 느리거나 한 프레임 늦어져도 명령 스트림은 일정하게 유지되어야 합니다.
"""

import argparse
import os
import sys
import threading
import time

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from command import Command
from controller import make_controller
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
                print(f"[카메라 오류] {e}")
                time.sleep(0.5)
                continue
            with self._lock:
                self._target = target
                self._n_det = len(detections)
                self._updated_at = time.monotonic()

    def latest(self, max_age):
        """최근 목표를 돌려줍니다. max_age 초보다 오래됐으면 None (= 정지)."""
        with self._lock:
            target, n_det, updated_at = self._target, self._n_det, self._updated_at
        if updated_at == 0.0 or time.monotonic() - updated_at > max_age:
            return None, n_det, True  # stale
        return target, n_det, False

    def stop(self):
        self._running = False
        self._thread.join(timeout=2.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(ROOT, "config.yaml"))
    ap.add_argument("--live", action="store_true", help="실제로 드론에 명령을 보냅니다")
    ap.add_argument("--no-mavlink", action="store_true", help="카메라만 테스트")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.live:
        cfg["safety"]["dry_run"] = False

    # 투하는 하방 카메라(과녁)일 때만 의미가 있습니다.
    # 사람을 따라가는 front 모드에서는 설정과 무관하게 절대 동작하지 않습니다.
    use_dropper = cfg["control"]["mode"] == "down" and cfg["dropper"]["enable"]
    if cfg["control"]["mode"] != "down":
        cfg["dropper"]["enable"] = False

    print("=" * 60)
    print(f"  제어 모드   : {cfg['control']['mode']}")
    print(f"  목표 클래스 : {cfg['detection']['target_class']}")
    print(f"  모델        : {os.path.basename(cfg['camera']['model'])}")
    print(f"  카메라      : {cfg['camera']['fps']} fps")
    print(f"  명령 전송   : {cfg['mavlink']['send_rate']} Hz")
    print(f"  드로퍼      : {'사용' if use_dropper else '사용 안 함'}")
    print(f"  모드        : {'*** LIVE ***' if not cfg['safety']['dry_run'] else 'DRY RUN (명령 안 보냄)'}")
    print("=" * 60)

    detector = Detector(cfg)
    tracker = Tracker(cfg, detector.frame_size)
    controller = make_controller(cfg)
    dropper = Dropper(cfg)
    judge = ReleaseJudge(cfg)
    link = None if args.no_mavlink else MavlinkLink(cfg)

    vision = VisionThread(detector, tracker)
    vision.start()

    period = 1.0 / cfg["mavlink"]["send_rate"]
    # 카메라가 이 시간 넘게 조용하면 목표를 버립니다.
    # 프레임 간격의 3배, 최소 1초. fps 가 낮아도 알아서 늘어납니다.
    max_age = max(1.0, 3.0 / cfg["camera"]["fps"])

    last_log = 0.0
    was_ready = False

    try:
        while True:
            loop_start = time.monotonic()

            target, n_det, stale = vision.latest(max_age)
            cmd = controller.compute(target)

            if link is not None:
                link.poll()
                ready, reason = link.ready_to_command()
                if ready and not was_ready:
                    link.statustext("TRACKING: guided control ON")
                was_ready = ready

                if not ready:
                    cmd = Command()

                # 목표가 없어도 '정지' 명령을 계속 보내야 합니다.
                # 명령이 끊기면 ArduPilot 이 GUIDED 를 종료합니다.
                link.send_velocity(cmd)
            else:
                ready, reason = False, "MAVLink 비활성"

            # 과녁 위에 잘 정렬됐으면 투하합니다. 판단은 release.py 가 합니다.
            if use_dropper:
                if judge.update(target, ready) and dropper.drop():
                    if link is not None:
                        link.statustext("DROP")
                dropper.update()   # 열어둔 시간이 지나면 스스로 닫힙니다

            now = time.monotonic()
            if now - last_log > 0.5:
                _log(target, cmd, reason, n_det, stale)
                if use_dropper:
                    print(f"     드로퍼: {judge.reason}"
                          f"{' | 투하 완료' if dropper.dropped else ''}")
                last_log = now

            time.sleep(max(0.0, period - (time.monotonic() - loop_start)))

    except KeyboardInterrupt:
        print("\n종료합니다.")
    finally:
        vision.stop()
        if link is not None:
            link.send_stop()
        dropper.stop()
        detector.close()


def _log(target, cmd, reason, n_det, stale):
    if stale:
        print(f"[!!] 카메라 정지 (프레임 안 들어옴) -> 정지 명령 | {reason}")
    elif target is None:
        print(f"[--] 목표 없음 (검출 {n_det}개) | {reason}")
    else:
        print(
            f"[OK] x={target.offset_x:+.2f} y={target.offset_y:+.2f} "
            f"size={target.size:.2f} conf={target.conf:.2f} "
            f"-> fwd={cmd.forward:+.2f} right={cmd.right:+.2f} down={cmd.down:+.2f}m/s "
            f"yaw={cmd.yaw_rate:+.1f}deg/s | {reason}"
        )


if __name__ == "__main__":
    main()
