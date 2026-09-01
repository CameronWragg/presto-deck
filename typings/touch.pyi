"""Stubs for `touch`, the FT6236 capacitive touch driver in the firmware.

Reached through `presto.touch`; most code wants `presto.touch_a` instead.
Written against presto v2.0.0 (modules/py_frozen/touch.py).
"""

class Button:
    x: int
    y: int
    w: int
    h: int
    pressed: bool

    def __init__(self, x: int, y: int, w: int, h: int) -> None: ...
    def is_pressed(self) -> bool: ...
    def bounds(self) -> tuple[int, int, int, int]: ...

class FT6236:
    x: int
    y: int
    state: bool
    x2: int
    y2: int
    state2: bool
    distance: float
    angle: float

    def __init__(
        self, full_res: bool = False, enable_interrupt: bool = False, rotate: int = 0
    ) -> None: ...
    def poll(self) -> None: ...
