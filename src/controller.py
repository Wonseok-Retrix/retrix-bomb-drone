"""config.yaml 의 control.mode 를 보고 제어기를 골라주는 파일.

실제 제어 로직은 여기 없습니다. 아래 두 파일 중 **하나만** 읽으면 됩니다.

    front  ->  controller_front.py   전방 카메라 / 사람 따라가기
    down   ->  controller_down.py    하방 카메라 / 과녁 따라가기

두 파일은 완전히 독립입니다. 한쪽을 고쳐도 다른 쪽은 절대 바뀌지 않습니다.
게인도 config.yaml 의 control.front / control.down 으로 따로 들고 있습니다.
"""

MODES = ("front", "down")


def make_controller(cfg):
    mode = cfg["control"]["mode"]
    if mode not in MODES:
        raise ValueError(f"control.mode 는 {' 또는 '.join(MODES)} 여야 합니다: {mode!r}")

    if mode == "front":
        from controller_front import Controller
    else:
        from controller_down import Controller

    # 자기 모드의 설정 블록만 넘겨줍니다. 다른 모드의 게인은 아예 보이지 않습니다.
    return Controller(cfg["control"][mode])
