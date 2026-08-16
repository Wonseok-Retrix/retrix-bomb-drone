"""서보 드로퍼 - 물건을 붙잡고 있다가 놓아주는 장치.

서보는 비행 컨트롤러를 거치지 않고 **라즈베리파이 GPIO 로 직접** 제어합니다.
FC 는 서보에 5V 전원만 공급합니다.

    FC 서보 레일 5V  ---->  서보 빨강
    FC 서보 레일 GND ---->  서보 갈색  + Pi GND (물리핀 6)   <- 접지 공통 필수
    Pi GPIO18 (물리핀 12) ->  서보 주황 (신호)

동작은 두 자세뿐입니다.

    closed_angle : 물건을 잡고 있는 각도
    open_angle   : 물건을 놓는 각도

drop() 을 부르면 열고, open_seconds 뒤에 스스로 닫습니다.
닫은 뒤에는 펄스를 끊어(detach) 서보가 떠는 것을 막습니다.

★ 이 클래스는 절대 스스로 drop() 하지 않습니다.
  언제 떨어뜨릴지는 release.py 가 판단합니다.
"""

import time


class Dropper:
    def __init__(self, cfg, live=False):
        d = cfg["dropper"]
        self.simulate = not live

        self.closed_angle = d["closed_angle"]
        self.open_angle = d["open_angle"]
        self.open_seconds = d["open_seconds"]

        self._servo = None
        self._dropped = False
        self._close_at = None
        self._detach_at = None

        if self.simulate:
            print("[DROPPER] simulation mode (DRY RUN) - servo will not move")
            return

        try:
            from gpiozero import AngularServo

            self._servo = AngularServo(
                d["pin"],
                min_angle=-90,
                max_angle=90,
                # 싼 서보(SG90 등)는 표준 범위를 벗어나므로 넓게 잡습니다.
                min_pulse_width=d["min_pulse_us"] / 1_000_000,
                max_pulse_width=d["max_pulse_us"] / 1_000_000,
            )
            print(f"[DROPPER] GPIO{d['pin']} servo ready")
            self.close()
        except Exception as e:
            # 서보가 없다고 비행이 멈추면 안 됩니다. 추적은 계속합니다.
            print(f"[DROPPER] could not initialize servo ({e}) - continuing in simulation")
            self.simulate = True

    @property
    def dropped(self):
        return self._dropped

    # ---------- 동작 ----------

    def drop(self):
        """물건을 놓습니다. 실제로 놓았으면 True."""
        if self._dropped:
            return False
        print("[DROPPER] ***** RELEASE *****")
        self._move(self.open_angle)
        self._dropped = True
        self._close_at = time.monotonic() + self.open_seconds
        self._detach_at = None
        return True

    def close(self):
        """물건을 잡는 자세로 되돌립니다."""
        self._move(self.closed_angle)
        self._close_at = None
        self._detach_at = time.monotonic() + 0.5   # 다 움직인 뒤 펄스를 끊습니다

    def update(self):
        """메인 루프에서 매번 호출. 시간이 되면 알아서 닫고 펄스를 끊습니다."""
        now = time.monotonic()
        if self._close_at is not None and now >= self._close_at:
            self.close()
        if self._detach_at is not None and now >= self._detach_at:
            self._detach()
            self._detach_at = None

    def reset(self):
        """다시 한 번 투하할 수 있도록 닫고 투하 상태를 초기화합니다."""
        self._dropped = False
        self.close()

    # ---------- 내부 ----------

    def _move(self, angle):
        if self.simulate or self._servo is None:
            print(f"[DROPPER] (simulation) servo {angle} deg")
            return
        self._servo.angle = angle

    def _detach(self):
        # 펄스를 끊으면 서보가 미세하게 떠는 것(지터)과 소음이 사라집니다.
        if self._servo is not None:
            self._servo.detach()

    def stop(self):
        """프로그램 종료 시 호출."""
        if self._servo is not None:
            self._detach()
            self._servo.close()
            self._servo = None
