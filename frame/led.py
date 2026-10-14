"""Optional dimmable LED on a GPIO pin (PWM)."""

from __future__ import annotations

import logging

log = logging.getLogger("frame.led")

GAMMA = 2.2  # perceived brightness is non-linear; keeps the dim end usable


class Led:
    def __init__(self, gpio: int | None):
        self.available = False
        self._led = None
        if gpio is None:
            return
        try:
            from gpiozero import PWMLED

            self._led = PWMLED(gpio, frequency=1000)
            self.available = True
            log.info("LED on GPIO%d ready", gpio)
        except Exception:
            log.exception("LED on GPIO%d could not be initialised", gpio)

    def apply(self, on: bool, brightness: int) -> None:
        if self._led is not None:
            self._led.value = (max(0, min(255, brightness)) / 255) ** GAMMA if on else 0.0

    def close(self) -> None:
        if self._led is not None:
            self._led.close()
