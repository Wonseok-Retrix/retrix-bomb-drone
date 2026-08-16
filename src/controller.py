"""하방 카메라로 과녁을 따라가는 제어기.

카메라가 아래를 보고 있을 때 화면의 오차를 RC 변환 전 추적 명령으로 바꿉니다.

    목표가 화면 오른쪽에 있다   ->  오른쪽으로 이동한다        (right)
    목표가 화면 위쪽에 있다     ->  앞으로 이동한다            (forward)
    박스가 목표보다 작다 (높다) ->  고도를 낮춘다              (down)

기수는 돌리지 않습니다(yaw = 0). 옆으로 미끄러지듯 움직여 과녁 위에 머무는 것이
이 모드의 성격입니다. 그래서 **카메라 위쪽이 기수 방향을 향하도록** 달아야
화면의 위/아래가 앞/뒤와 맞습니다.

읽는 설정은 config.yaml 의 control 블록 뿐입니다.

P 제어는 "오차에 비례해서 반응한다"가 전부입니다. gain=1이면 데드밴드 바깥의
최대 오차에서 해당 RC 스틱 끝값까지 사용합니다.

    정규화 명령 = 정규화 오차 x gain      (최종 범위 -1 ~ +1)


★ 느린 카메라(1~2 fps)를 위한 감쇠
------------------------------------------------------------------
이 카메라는 초당 1~2장밖에 못 줍니다. 즉 한 번 본 위치는 최대 1초까지
"옛날 정보"인 채로 남습니다. 그 사이에 같은 속도로 계속 밀고 나가면
목표를 지나쳐버리고(오버슈트), 다음 프레임에서 반대로 꺾으면서
좌우로 크게 흔들리게 됩니다.

그래서 명령에 **나이(age)** 를 곱합니다.

    age <= stale_hold            : 그대로 (방금 본 정보)
    stale_hold ~ stale_stop      : 선형으로 줄어듦
    age >= stale_stop            : 0 (완전 정지)

결과적으로 "한 프레임 보고 -> 조금 움직이고 -> 스스로 멈춰서 기다리기" 가 됩니다.
느리지만 절대 폭주하지 않습니다. 정확도보다 안정성을 택한 설정입니다.
"""

from command import Command


def _deadband(value, band):
    """데드밴드 바깥을 0~1로 다시 늘려 최대 오차가 정확히 1이 되게 합니다."""
    if abs(value) <= band:
        return 0.0
    magnitude = (abs(value) - band) / (1.0 - band)
    return _clamp(magnitude, 1.0) * (1.0 if value > 0 else -1.0)


def _size_error(size, target_size, band):
    """목표 크기 오차를 상승/하강 방향별 최대 가능 오차로 정규화합니다."""
    raw = target_size - size
    if abs(raw) <= band:
        return 0.0
    limit = target_size if raw > 0 else 1.0 - target_size
    if limit <= band:
        return 0.0
    magnitude = (abs(raw) - band) / (limit - band)
    return _clamp(magnitude, 1.0) * (1.0 if raw > 0 else -1.0)


def _clamp(value, limit):
    return max(-limit, min(limit, value))


class Controller:
    def __init__(self, c):
        # 구 config.yaml도 실행 가능하도록 새 키가 없으면 보수적인 기본값을 씁니다.
        self.lateral_gain = c.get("lateral_gain", 0.25)
        self.forward_gain = c.get("forward_gain", 0.25)
        self.vertical_gain = c.get("vertical_gain", 0.10)

        self.deadband = c["deadband"]
        self.target_size = c["target_size"]
        self.size_deadband = c["size_deadband"]

        self.stale_hold = c["stale_hold"]
        self.stale_stop = c["stale_stop"]

    def freshness(self, age):
        """목표 정보의 나이 -> 명령에 곱할 비율 (1.0 ~ 0.0)."""
        if age <= self.stale_hold:
            return 1.0
        if age >= self.stale_stop:
            return 0.0
        span = self.stale_stop - self.stale_hold
        return 1.0 - (age - self.stale_hold) / span

    def compute(self, target, age=0.0):
        """Target -> Command.

        target 이 None 이거나 너무 오래된 정보면 정지 명령(= 제자리 호버).
        age 는 이 목표를 마지막으로 실제로 본 뒤 흐른 시간(초)입니다.
        """
        if target is None:
            return Command()

        scale = self.freshness(age)
        if scale <= 0.0:
            return Command()

        # 1) 좌우: 목표가 오른쪽에 있으면 오른쪽으로 이동 (기수는 그대로)
        err_x = _deadband(target.offset_x, self.deadband)
        right = _clamp(err_x * self.lateral_gain, 1.0)

        # 2) 상하: 화면 위쪽(-)이 기수 앞쪽이므로 부호를 뒤집는다
        err_y = _deadband(target.offset_y, self.deadband)
        forward = _clamp(-err_y * self.forward_gain, 1.0)

        # 3) 크기: 박스가 목표 크기보다 작으면(= 아직 높으면) 하강
        err_size = _size_error(target.size, self.target_size, self.size_deadband)
        down = _clamp(err_size * self.vertical_gain, 1.0)

        # 4) 정보가 오래될수록 힘을 뺍니다 (위 주석 참고)
        return Command(
            forward=forward * scale,
            right=right * scale,
            down=down * scale,
        )
