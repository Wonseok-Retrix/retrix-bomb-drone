"""언제 물건을 떨어뜨릴지 판단하는 파일.

과녁 위에 "충분히 잘" 올라갔는지만 봅니다. 조건은 네 개입니다.

    1. 과녁이 보인다
    2. 과녁이 화면 중앙에 있다            (align  보다 오차가 작다)
    3. 충분히 낮게 내려왔다               (박스 크기가 size_min 보다 크다)
    4. 위 상태가 hold_seconds 동안 유지됐다

하나라도 깨지면 타이머는 0으로 돌아갑니다. 지나가면서 우연히 중앙에 걸린 순간에
떨어뜨리지 않기 위해서입니다.

드로퍼가 카메라 바로 밑에 있지 않으면 aim_x / aim_y 로 조준점을 옮깁니다.
(예: 드로퍼가 카메라보다 뒤에 달렸으면 과녁을 화면 위쪽에 두고 놔야 합니다)
"""

import time


class ReleaseJudge:
    def __init__(self, cfg):
        r = cfg["dropper"]["release"]
        self.align = r["align"]
        self.size_min = r["size_min"]
        self.hold_seconds = r["hold_seconds"]
        self.aim_x = r["aim_x"]
        self.aim_y = r["aim_y"]

        self._good_since = None
        self.reason = "대기"

    def update(self, target, ready):
        """조건을 다 만족하면 딱 한 번 True. 매 루프 호출하세요."""
        ok, self.reason = self._check(target, ready)

        if not ok:
            self._good_since = None
            return False

        now = time.monotonic()
        if self._good_since is None:
            self._good_since = now

        held = now - self._good_since
        if held < self.hold_seconds:
            self.reason = f"정렬 유지중 {held:.1f}/{self.hold_seconds:.1f}s"
            return False

        self.reason = "투하 조건 충족"
        self._good_since = None
        return True

    def _check(self, target, ready):
        if not ready:
            return False, "제어 불가 상태"       # GUIDED 아님 / 시동 안 걸림
        if target is None:
            return False, "과녁 안 보임"

        dx = target.offset_x - self.aim_x
        dy = target.offset_y - self.aim_y
        if abs(dx) > self.align or abs(dy) > self.align:
            return False, f"중앙에서 벗어남 ({dx:+.2f}, {dy:+.2f})"

        if target.size < self.size_min:
            return False, f"아직 높음 (크기 {target.size:.2f} < {self.size_min:.2f})"

        return True, "정렬됨"
