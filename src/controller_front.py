"""[전방 카메라 / 사람 따라가기] 제어기.

카메라가 앞을 보고 있을 때 화면의 오차를 속도 명령으로 바꿉니다.

    목표가 화면 오른쪽에 있다   ->  기수를 오른쪽으로 돌린다   (yaw)
    박스가 목표보다 작다 (멀다) ->  앞으로 간다               (forward)
    목표가 화면 아래쪽에 있다   ->  고도를 낮춘다             (vertical, 기본 OFF)

옆으로 미끄러지듯 움직이지 않고 "기수를 돌려서 쫓아간다"가 이 모드의 성격입니다.

읽는 설정은 config.yaml 의 control.front 뿐입니다.
하방 카메라(과녁)는 controller_down.py 에 따로 있습니다. 서로 영향을 주지 않으니
이 파일은 마음껏 고쳐도 됩니다.

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
        self.yaw_gain = c["yaw_gain"]
        self.forward_gain = c["forward_gain"]
        self.vertical_gain = c["vertical_gain"]

        self.max_yaw_rate = c["max_yaw_rate"]
        self.max_forward = c["max_forward"]
        self.max_vertical = c["max_vertical"]

        self.deadband = c["deadband"]
        self.target_size = c["target_size"]
        self.size_deadband = c["size_deadband"]
        self.enable_vertical = c["enable_vertical"]

    def compute(self, target):
        """Target -> Command. target 이 None 이면 정지 명령(= 제자리 호버)."""
        if target is None:
            return Command()

        # 1) 좌우: 목표가 오른쪽에 있으면 기수를 오른쪽으로 돌린다
        err_x = _deadband(target.offset_x, self.deadband)
        yaw_rate = _clamp(err_x * self.yaw_gain * self.max_yaw_rate, self.max_yaw_rate)

        # 2) 크기: 박스가 목표 크기보다 작으면(= 멀면) 전진
        err_size = _deadband(self.target_size - target.size, self.size_deadband)
        forward = _clamp(err_size * self.forward_gain * self.max_forward, self.max_forward)

        # 3) 상하: 목표가 화면 아래쪽에 있으면 고도를 낮춘다 (옵션)
        down = 0.0
        if self.enable_vertical:
            err_y = _deadband(target.offset_y, self.deadband)
            down = _clamp(err_y * self.vertical_gain * self.max_vertical, self.max_vertical)

        return Command(forward=forward, down=down, yaw_rate=yaw_rate)
