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
        self._continuous = False
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

    def notify_cycle(self, tracking=None, release_waiting=False):
        """Play frame beeps and keep release waiting as a continuous tone."""
        if not self.enabled:
            return

        if release_waiting:
            pattern = ()
            continuous = True
        elif tracking is None:
            # No new camera frame. Only stop a continuous release-waiting tone.
            if not self._continuous:
                return
            pattern = ()
            continuous = False
        elif not tracking:
            pattern = ()
            continuous = False
        else:
            pattern = ((self.BEEP_SECONDS, 0.0),)
            continuous = False

        with self._condition:
            # Do not restart the continuous tone on every control-loop cycle.
            if continuous and self._continuous:
                return
            self._pattern = pattern
            self._continuous = continuous
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
                continuous = self._continuous
                handled = self._generation
            if continuous:
                self._play_continuous(handled)
            else:
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

    def _play_continuous(self, generation):
        self._output.on()
        with self._condition:
            self._condition.wait_for(
                lambda: self._stopped or self._generation != generation
            )
        self._off()

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
