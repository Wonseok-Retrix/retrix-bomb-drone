"""Active buzzer status sounds, played without blocking the flight loop."""

import threading
import time


class StatusBuzzer:
    """Play the latest requested status pattern on an active GPIO buzzer."""

    PIN = 23  # BCM GPIO23, physical pin 16
    BEEP_SECONDS = 0.06
    CYCLE_INTERVAL = 0.13
    RELEASE_BEEPS_PER_SECOND = 6
    RELEASE_INTERVAL = 1.0 / RELEASE_BEEPS_PER_SECOND
    STARTUP_BEEPS = 3

    def __init__(self):
        self.enabled = True
        self._output = None
        self._condition = threading.Condition()
        self._generation = 0
        self._pattern = ()
        self._repeat_interval = None
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
        """Update status, keeping the release-ready sound independent of frames."""
        if not self.enabled:
            return

        repeat_interval = None
        if release_waiting:
            pattern = ((self.BEEP_SECONDS, 0.0),)
            repeat_interval = self.RELEASE_INTERVAL
        elif not tracking:
            pattern = ()
        else:
            pattern = ((self.BEEP_SECONDS, 0.0),)

        with self._condition:
            # Camera frames may arrive faster than the release-ready cadence.
            # Do not restart an already-running cadence for every frame.
            if repeat_interval is not None and self._repeat_interval is not None:
                return
            self._pattern = pattern
            self._repeat_interval = repeat_interval
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
                repeat_interval = self._repeat_interval
                handled = self._generation
            if repeat_interval is None:
                self._play(pattern, generation=handled)
            else:
                self._play_repeating(repeat_interval, handled)

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

    def _play_repeating(self, interval, generation):
        """Repeat from fixed deadlines so processing time cannot shift the cadence."""
        next_start = time.monotonic()
        while True:
            if not self._wait_until(next_start, generation):
                return
            self._output.on()
            if not self._wait(self.BEEP_SECONDS, generation):
                self._off()
                return
            self._off()

            next_start += interval
            now = time.monotonic()
            if next_start < now:
                missed = int((now - next_start) / interval) + 1
                next_start += missed * interval

    def _wait_until(self, deadline, generation):
        with self._condition:
            while not self._stopped:
                if self._generation != generation:
                    return False
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return True
                self._condition.wait(remaining)
        return False

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
