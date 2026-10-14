"""Optional dimmable LED on a GPIO pin (PWM).

On GPIO12/18 the Pi's hardware PWM is used (flicker-free, needs the `pwm` device-tree
overlay, see docs/led.md). Other pins, or a missing overlay, fall back to software PWM
via gpiozero, which can flicker at very low brightness.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

log = logging.getLogger("frame.led")

GAMMA = 2.2  # perceived brightness is non-linear; keeps the dim end usable
MIN_DUTY = 0.0004  # lowest duty that still lights the LED (brightness 1)
PWM_PERIOD_NS = 500_000  # 2 kHz
HW_PWM_PINS = {12, 18}  # PWM0 channel 0 with `dtoverlay=pwm,pin=<pin>`
SYSFS_PWM = Path("/sys/class/pwm")


def _duty(on: bool, brightness: int) -> float:
    if not on or brightness <= 0:
        return 0.0
    return max((min(brightness, 255) / 255) ** GAMMA, MIN_DUTY)


class _HardwarePwm:
    def __init__(self) -> None:
        chips = sorted(SYSFS_PWM.glob("pwmchip*"))
        if not chips:
            raise OSError("no PWM chip (pwm overlay missing?)")
        chip = chips[0]
        self._pwm = chip / "pwm0"
        if not self._pwm.exists():
            (chip / "export").write_text("0")
        # udev hands the freshly exported files to the gpio group a moment later
        period = self._pwm / "period"
        for _ in range(50):
            if os.access(period, os.W_OK):
                break
            time.sleep(0.1)
        period.write_text(str(PWM_PERIOD_NS))
        (self._pwm / "duty_cycle").write_text("0")
        (self._pwm / "enable").write_text("1")

    def set(self, duty: float) -> None:
        (self._pwm / "duty_cycle").write_text(str(int(duty * PWM_PERIOD_NS)))

    def close(self) -> None:
        self.set(0.0)
        (self._pwm / "enable").write_text("0")


class _SoftwarePwm:
    def __init__(self, gpio: int) -> None:
        from gpiozero import PWMLED

        self._led = PWMLED(gpio, frequency=1000)

    def set(self, duty: float) -> None:
        self._led.value = duty

    def close(self) -> None:
        self._led.close()


class Led:
    def __init__(self, gpio: int | None):
        self.available = False
        self._backend: _HardwarePwm | _SoftwarePwm | None = None
        if gpio is None:
            return
        if gpio in HW_PWM_PINS:
            try:
                self._backend = _HardwarePwm()
                log.info("LED on GPIO%d ready (hardware PWM)", gpio)
            except OSError as err:
                log.warning("Hardware PWM unavailable (%s), using software PWM", err)
        if self._backend is None:
            try:
                self._backend = _SoftwarePwm(gpio)
                log.info("LED on GPIO%d ready (software PWM)", gpio)
            except Exception:
                log.exception("LED on GPIO%d could not be initialised", gpio)
                return
        self.available = True

    def apply(self, on: bool, brightness: int) -> None:
        if self._backend is not None:
            self._backend.set(_duty(on, brightness))

    def close(self) -> None:
        if self._backend is not None:
            self._backend.close()
