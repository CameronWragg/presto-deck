"""Stubs for the `presto` module frozen into the Presto firmware.

Written against presto v2.0.0 (modules/py_frozen/presto.py). These describe
what is on the board - they are not importable on the host, and nothing here
is used at runtime.

https://github.com/pimoroni/presto/blob/main/docs/presto.md
"""

from typing import NamedTuple

from ezwifi import EzWiFi
from picographics import PicoGraphics
from touch import FT6236

ROTATE_0: int
ROTATE_180: int

class Touch(NamedTuple):
    """`presto.touch_a` / `presto.touch_b` - a namedtuple, so both
    `x, y, touched = presto.touch_a` and `presto.touch_a.touched` work."""

    x: int
    y: int
    touched: bool

class Buzzer:
    def __init__(self, pin: int) -> None: ...
    def set_tone(self, freq: float, duty: float = 0.5) -> bool: ...

class Presto:
    NUM_LEDS: int = 7
    LED_PIN: int = 33

    display: PicoGraphics
    wifi: EzWiFi
    touch: FT6236
    width: int
    height: int

    def __init__(
        self,
        full_res: bool = False,
        palette: bool = False,
        ambient_light: bool = False,
        direct_to_fb: bool = False,
        layers: int | None = None,
        rotate: int = 0,
    ) -> None:
        """480x480 with `full_res=True`, 240x240 (upscaled) otherwise."""

    @property
    def touch_a(self) -> Touch: ...
    @property
    def touch_b(self) -> Touch: ...
    @property
    def touch_delta(self) -> tuple[float, float]:
        """(distance, angle) between the two touch points."""

    def touch_poll(self) -> None: ...
    def connect(self, ssid: str | None = None, password: str | None = None) -> bool:
        """Blocking connect. Falls back to WIFI_SSID/WIFI_PASSWORD in secrets.py."""

    async def async_connect(self) -> None: ...
    def set_backlight(self, brightness: float) -> None:
        """0.0 - 1.0."""

    def auto_ambient_leds(self, enable: bool) -> None: ...
    def set_led_rgb(self, i: int, r: int, g: int, b: int) -> None:
        """LED 0-6, channels 0-255."""

    def set_led_hsv(self, i: int, h: float, s: float, v: float) -> None: ...
    def update(self) -> None:
        """Present the framebuffer, and poll touch."""

    def partial_update(self, x: int, y: int, w: int, h: int) -> None: ...
    def clear(self) -> None: ...
