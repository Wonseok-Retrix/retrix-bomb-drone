"""하방 카메라로 과녁을 따라가는 제어기.

카메라가 아래를 보고 있을 때 화면의 오차를 속도 명령으로 바꿉니다.

    목표가 화면 오른쪽에 있다   ->  오른쪽으로 이동한다        (right)
    목표가 화면 위쪽에 있다     ->  앞으로 이동한다            (forward)
    박스가 목표보다 작다 (높다) ->  고도를 낮춘다              (vertical)

기수는 돌리지 않습니다(yaw = 0). 옆으로 미끄러지듯 움직여 과녁 위에 머무는 것이
이 모드의 성격입니다. 그래서 **카메라 위쪽이 기수 방향을 향하도록** 달아야
화면의 위/아래가 앞/뒤와 맞습니다.

읽는 설정은 config.yaml 의 control 블록 뿐입니다.

P 제어는 "오차에 비례해서 반응한다"가 전부입니다.
게인(gain)을 키우면 빠르지만 흔들리고, 줄이면 안정적이지만 굼뜹니다.

    명령 = 오차 x 게인 x 최대속도      (단, 최대속도를 넘지 않음)
"""

from command import Command


def _deadband(value, band):
    """작은 오차는 0으로 죽이고, 그 바깥은 연속적으로 이어붙입니다."""
    if abs(value) <= band:
        return 0.0
    return value - band if value > 0 else value + band


def _clamp(value, limit):
    return max(-limit, min(limit, value))


class Controller:
    def __init__(self, c):
        self.lateral_gain = c["lateral_gain"]
        self.forward_gain = c["forward_gain"]
        self.vertical_gain = c["vertical_gain"]

        self.max_lateral = c["max_lateral"]
        self.max_forward = c["max_forward"]
        self.max_vertical = c["max_vertical"]

        self.deadband = c["deadband"]
        self.target_size = c["target_size"]
        self.size_deadband = c["size_deadband"]

    def compute(self, target):
        """Target -> Command. target 이 None 이면 정지 명령(= 제자리 호버)."""
        if target is None:
            return Command()

        # 1) 좌우: 목표가 오른쪽에 있으면 오른쪽으로 이동 (기수는 그대로)
        err_x = _deadband(target.offset_x, self.deadband)
        right = _clamp(err_x * self.lateral_gain * self.max_lateral, self.max_lateral)

        # 2) 상하: 화면 위쪽(-)이 기수 앞쪽이므로 부호를 뒤집는다
        err_y = _deadband(target.offset_y, self.deadband)
        forward = _clamp(-err_y * self.forward_gain * self.max_forward, self.max_forward)

        # 3) 크기: 박스가 목표 크기보다 작으면(= 아직 높으면) 하강
        err_size = _deadband(self.target_size - target.size, self.size_deadband)
        down = _clamp(err_size * self.vertical_gain * self.max_vertical, self.max_vertical)

        return Command(forward=forward, right=right, down=down)
