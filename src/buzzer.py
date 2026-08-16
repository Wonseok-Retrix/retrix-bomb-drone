"""Active buzzer status sounds, played without blocking the flight loop."""

import threading
import time


class StatusBuzzer:
    """Play the latest requested status pattern on an active GPIO buzzer."""

    PIN = 23  # BCM GPIO23, physical pin 16
    BEEP_SECONDS = 0.06
    CYCLE_INTERVAL = 0.13
    STARTUP_BEEPS = 3

    def __init__(self):
        self.enabled = True
        self._output = None
        self._condition = threading.Condition()
        self._generation = 0
        self._pattern = ()
        self._stopped = False
        self._thread = None

        try:
            from gpiozero import DigitalOutputDevice

            self._output = DigitalOutputDevice(
                self.PIN, active_high=True, initial_value=False
            )
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
            print(f"[BUZZER] active buzzer ready on GPIO{self.PIN}")
        except Exception as e:
            # A buzzer failure must not stop tracking or flight control.
            print(f"[BUZZER] could not initialize ({e}) - sounds disabled")
            self.enabled = False
            if self._output is not None:
                self._output.close()
                self._output = None

    def notify_cycle(self, tracking, release_waiting=False):
        """Announce one new camera cycle, replacing any unfinished status sound."""
        if not self.enabled:
            return

        if not tracking:
            pattern = ()
        else:
            count = 3 if release_waiting else 1
            gap = max(0.0, self.CYCLE_INTERVAL - self.BEEP_SECONDS)
            pattern = tuple(
                (self.BEEP_SECONDS, gap if i < count - 1 else 0.0)
                for i in range(count)
            )

        with self._condition:
            self._pattern = pattern
            self._generation += 1
            self._condition.notify_all()

    def _loop(self):
        gap = max(0.0, self.CYCLE_INTERVAL - self.BEEP_SECONDS)
        startup = tuple(
            (self.BEEP_SECONDS, gap if i < self.STARTUP_BEEPS - 1 else 0.0)
            for i in range(self.STARTUP_BEEPS)
        )
        self._play(startup, generation=None)

        handled = 0
        while True:
            with self._condition:
                self._condition.wait_for(
                    lambda: self._stopped or self._generation != handled
                )
                if self._stopped:
                    break
                pattern = self._pattern
                handled = self._generation
            self._play(pattern, generation=handled)

        self._off()

    def _play(self, pattern, generation):
        for duration, gap in pattern:
            if not self._wait(0.0, generation):
                return
            self._output.on()
            if not self._wait(duration, generation):
                self._off()
                return
            self._off()
            if not self._wait(gap, generation):
                return

    def _wait(self, seconds, generation):
        deadline = time.monotonic() + seconds
        with self._condition:
            while not self._stopped:
                if generation is not None and self._generation != generation:
                    return False
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return True
                self._condition.wait(remaining)
        return False

    def _off(self):
        if self._output is not None:
            self._output.off()

    def stop(self):
        """Silence and release the GPIO device."""
        if self._thread is None:
            return
        with self._condition:
            self._stopped = True
            self._condition.notify_all()
        self._thread.join(timeout=2.0)
        self._off()
        self._output.close()
        self._output = None
        self._thread = None
