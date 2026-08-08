"""비행 컨트롤러에 보낼 속도 명령 한 덩어리.

제어기(controller_front.py / controller_down.py)가 이걸 만들고,
mavlink_link.py 가 이걸 그대로 MAVLink 로 보냅니다.
"""

from dataclasses import dataclass


@dataclass
class Command:
    """기체 기준 좌표계. 아무것도 안 넣으면 '정지'(= 제자리 호버) 명령입니다."""

    forward: float = 0.0   # m/s, + 전진
    right: float = 0.0     # m/s, + 오른쪽
    down: float = 0.0      # m/s, + 하강
    yaw_rate: float = 0.0  # deg/s, + 시계방향

    @property
    def is_stop(self):
        return self.forward == self.right == self.down == self.yaw_rate == 0.0
