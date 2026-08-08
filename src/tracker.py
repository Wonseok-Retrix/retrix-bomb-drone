"""여러 검출 결과 중 '쫓아갈 하나'를 골라서 계속 따라가는 모듈.

검출(detection)은 매 프레임 독립적이라 깜빡거립니다.
추적(tracking)은 그걸 이어붙여서 하나의 목표로 만들어 줍니다.
"""

import time


class Target:
    """추적 중인 목표 하나. 화면 기준 정규화 좌표를 제공합니다."""

    def __init__(self, box, conf, frame_size):
        self.box = box
        self.conf = conf
        self.frame_w, self.frame_h = frame_size

    @property
    def offset_x(self):
        """화면 중심 대비 좌우 오차. -1(왼쪽 끝) ~ +1(오른쪽 끝)"""
        cx = self.box[0] + self.box[2] / 2
        return (cx - self.frame_w / 2) / (self.frame_w / 2)

    @property
    def offset_y(self):
        """화면 중심 대비 상하 오차. -1(위) ~ +1(아래)"""
        cy = self.box[1] + self.box[3] / 2
        return (cy - self.frame_h / 2) / (self.frame_h / 2)

    @property
    def size(self):
        """화면 높이 대비 목표 박스 높이. 클수록 가까움."""
        return self.box[3] / self.frame_h


class Tracker:
    def __init__(self, cfg, frame_size):
        t = cfg["tracking"]
        self.target_class = cfg["detection"]["target_class"]
        self.smoothing = t["smoothing"]
        self.lost_timeout = t["lost_timeout"]
        self.select = t["select"]
        self.frame_size = frame_size

        self._box = None  # 평활화된 박스
        self._conf = 0.0
        self._last_seen = 0.0

    def update(self, detections):
        """검출 리스트를 넣으면 현재 Target 또는 None 을 돌려줍니다."""
        candidates = [d for d in detections if d.label == self.target_class]
        now = time.monotonic()

        if candidates:
            best = self._pick(candidates)
            if self._box is None:
                self._box = best.box
            else:
                a = self.smoothing
                self._box = tuple(a * n + (1 - a) * o for n, o in zip(best.box, self._box))
            self._conf = best.conf
            self._last_seen = now

        elif now - self._last_seen > self.lost_timeout:
            # 너무 오래 못 봤으면 추적 포기
            self._box = None
            self._conf = 0.0
            return None

        if self._box is None:
            return None
        return Target(self._box, self._conf, self.frame_size)

    def _pick(self, candidates):
        if self.select == "largest":
            return max(candidates, key=lambda d: d.box[2] * d.box[3])

        if self.select == "nearest" and self._box is not None:
            px = self._box[0] + self._box[2] / 2
            py = self._box[1] + self._box[3] / 2
            return min(
                candidates,
                key=lambda d: (d.center[0] - px) ** 2 + (d.center[1] - py) ** 2,
            )

        return max(candidates, key=lambda d: d.conf)
