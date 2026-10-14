# Dimmable mini LED on two wires

One LED, two wires: GPIO18 → resistor → LED → GND. The software dims it with
PWM (1 kHz, gamma-corrected) and exposes it to Home Assistant as `light.inky_frame_led`.

```
Pi pin 12 (GPIO18) ──[ 100 Ω ]──►|── Pi pin 14 (GND)
                                 LED (anode → cathode)
```

* **Why GPIO18?** It is free on the Inky Impression (which uses SPI, GPIO 17/22/27 and the
  buttons on 5/6/16/24). Double-check with Pimoroni's pin table for your exact model before wiring.
* **Resistor:** a warm-white 0603 LED has Vf ≈ 2.8–3.2 V, the GPIO delivers 3.3 V, so only a
  small resistor is needed. Start with 100 Ω (≈ 2–5 mA, plenty bright for a mini accent light).
  Never go below ~47 Ω; keep the GPIO current under ~8 mA. The 5 V/9 V/14 V resistors shipped
  with LED kits are **not** for 3.3 V — don't use them.
* **No transistor needed** at these currents.
* **Polarity:** if it doesn't light, swap the two wires. (The LED is a diode.)
* **Getting to the pins:** the Inky Impression sits on the header. Solder the two wires (with the
  resistor in line, heat-shrink over it) to the pads of pin 12 and pin 14 on the underside of the Pi,
  or use a tall stacking header and female Dupont wires.

Enable in `frame/.env`:

```
LED_GPIO=18
```

then `sudo systemctl restart inky-frame`. Brightness and state are remembered across restarts.
