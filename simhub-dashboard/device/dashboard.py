"""Screen layout for the SimHub dashboard.

Everything is laid out from display.get_bounds() against a 240x240 design
grid, so the same code fills the screen in both normal and full_res mode.
"""

BASE = 240  # the design grid this layout was drawn on


class TextRenderer:
    """Text via PicoVector when a font is available, bitmap font otherwise.

    Numbers are drawn into fixed width cells so a big readout doesn't jitter
    as digits change width.
    """

    def __init__(self, display, font_path=None):
        self.display = display
        self.vector = None
        self._cell_cache = {}
        self._wrap = display.get_bounds()[0]
        display.set_font("bitmap8")
        if font_path:
            self._try_vector(font_path)

    def _try_vector(self, font_path):
        try:
            from picovector import ANTIALIAS_X4, PicoVector, Transform

            vector = PicoVector(self.display)
            vector.set_antialiasing(ANTIALIAS_X4)
            vector.set_transform(Transform())
            vector.set_font(font_path, 24)
            self.vector = vector
        except Exception:  # noqa: BLE001 - no font on device, bitmap is fine
            self.vector = None

    # -- measuring -----------------------------------------------------------

    def measure(self, text, size):
        """(width, height) of `text` drawn at `size` pixels tall."""
        if self.vector:
            try:
                self.vector.set_font_size(int(size))
                _x, _y, width, _height = self.vector.measure_text(text)
                return int(width), int(size)
            except Exception:  # noqa: BLE001
                self.vector = None
        scale = self._scale(size)
        return self.display.measure_text(text, scale), 8 * scale

    def _scale(self, size):
        return max(1, int(size / 8 + 0.5))

    def _cell(self, size):
        """Width of the widest digit at this size, cached."""
        width = self._cell_cache.get(size)
        if width is None:
            width = max(self.measure(c, size)[0] for c in "0123456789")
            self._cell_cache[size] = width
        return width

    # -- drawing -------------------------------------------------------------

    def draw(self, text, x, y, size, align="left"):
        """Draw `text` with its top-left/top-centre/top-right at (x, y)."""
        width, height = self.measure(text, size)
        if align == "centre":
            x -= width // 2
        elif align == "right":
            x -= width
        self._draw_at(text, int(x), int(y), size)
        return width, height

    def draw_number(self, text, x, y, size, align="left"):
        """Draw digits in fixed width cells so the readout stays put."""
        cell = self._cell(size)
        width = cell * len(text)
        if align == "centre":
            x -= width // 2
        elif align == "right":
            x -= width
        for index, char in enumerate(text):
            char_width, _height = self.measure(char, size)
            offset = (cell - char_width) // 2
            self._draw_at(char, int(x + index * cell + offset), int(y), size)
        return width, size

    def _draw_at(self, text, x, y, size):
        if self.vector:
            try:
                self.vector.set_font_size(int(size))
                # PicoVector places text on its baseline; our y is the top.
                self.vector.text(text, x, int(y + size * 0.78))
                return
            except Exception:  # noqa: BLE001
                self.vector = None
        self.display.text(text, x, y, self._wrap, self._scale(size))


class Dashboard:
    SEGMENTS = 16

    def __init__(self, presto, font_path=None, shift_start=0.80, shift_flash=0.97):
        self.presto = presto
        self.display = presto.display
        self.width, self.height = self.display.get_bounds()
        self.scale = self.width / BASE
        self.shift_start = shift_start
        self.shift_flash = shift_flash
        self.text = TextRenderer(self.display, font_path)

        create = self.display.create_pen
        self.BG = create(8, 8, 12)
        self.PANEL = create(24, 26, 32)
        self.DIM = create(70, 75, 85)
        self.LABEL = create(130, 140, 155)
        self.WHITE = create(255, 255, 255)
        self.GREEN = create(0, 220, 90)
        self.AMBER = create(255, 176, 0)
        self.RED = create(255, 40, 40)
        self.BLUE = create(60, 170, 255)
        self.OFF = create(28, 30, 36)

    def _s(self, value):
        """Scale a design-grid measurement to the real display."""
        return int(value * self.scale)

    # -- public --------------------------------------------------------------

    def splash(self, title, subtitle=""):
        self.display.set_pen(self.BG)
        self.display.clear()
        self.display.set_pen(self.WHITE)
        self.text.draw(title, self.width // 2, self._s(100), self._s(20), "centre")
        if subtitle:
            self.display.set_pen(self.LABEL)
            self.text.draw(subtitle, self.width // 2, self._s(130), self._s(12), "centre")
        self.presto.update()

    def render(self, tel, units, live, status, now_ms):
        self.display.set_pen(self.BG)
        self.display.clear()
        self._rev_bar(tel, now_ms)
        self._speed(tel, units, live)
        self._gear(tel)
        self._rpm(tel)
        self._status(live, status)
        self.presto.update()

    def segment_colours(self, fraction, now_ms):
        """The rev bar as a list of (lit, pen) - also drives the LEDs."""
        flashing = fraction >= self.shift_flash and (now_ms // 60) % 2 == 0
        lit_count = int(fraction * self.SEGMENTS + 0.5)
        out = []
        for index in range(self.SEGMENTS):
            position = (index + 1) / self.SEGMENTS
            if flashing:
                out.append((True, self.BLUE))
                continue
            if index >= lit_count:
                out.append((False, self.OFF))
            elif position > 0.90:
                out.append((True, self.RED))
            elif position > 0.72:
                out.append((True, self.AMBER))
            else:
                out.append((True, self.GREEN))
        return out

    # -- panels --------------------------------------------------------------

    def _rev_bar(self, tel, now_ms):
        x0 = self._s(6)
        y0 = self._s(8)
        height = self._s(30)
        total = self.width - 2 * x0
        gap = max(1, self._s(2))
        segment = (total - gap * (self.SEGMENTS - 1)) / self.SEGMENTS

        for index, (_lit, pen) in enumerate(self.segment_colours(tel.rev_fraction, now_ms)):
            self.display.set_pen(pen)
            self.display.rectangle(
                int(x0 + index * (segment + gap)), y0, int(segment), height
            )

    def _speed(self, tel, units, live):
        speed = tel.speed(units)
        digits = "{:.0f}".format(speed) if live else "--"
        self.display.set_pen(self.WHITE if live else self.DIM)
        self.text.draw_number(digits, self.width // 2, self._s(48), self._s(76), "centre")
        self.display.set_pen(self.LABEL)
        self.text.draw(
            "MPH" if units == "mph" else "KM/H",
            self.width // 2, self._s(130), self._s(14), "centre",
        )

    def _gear(self, tel):
        x, y = self._s(6), self._s(152)
        width, height = self._s(72), self._s(60)
        self.display.set_pen(self.PANEL)
        self.display.rectangle(x, y, width, height)
        self.display.set_pen(self.AMBER if tel.shifting else self.WHITE)
        self.text.draw(
            str(tel.gear)[:1], x + width // 2, y + self._s(8), self._s(44), "centre"
        )

    def _rpm(self, tel):
        x, y = self._s(84), self._s(152)
        width, height = self.width - x - self._s(6), self._s(60)
        self.display.set_pen(self.PANEL)
        self.display.rectangle(x, y, width, height)

        self.display.set_pen(self.LABEL)
        self.text.draw("RPM", x + self._s(8), y + self._s(6), self._s(11))
        self.display.set_pen(self.WHITE)
        self.text.draw_number(
            "{:.0f}".format(tel.rpm), x + width - self._s(8), y + self._s(20),
            self._s(30), "right",
        )
        # Redline reference, so you can see what the bar is scaled to.
        self.display.set_pen(self.DIM)
        self.text.draw(
            "/ {:.0f}".format(tel.max_rpm), x + self._s(8), y + self._s(40), self._s(11)
        )

    def _status(self, live, status):
        y = self.height - self._s(20)
        self.display.set_pen(self.PANEL)
        self.display.rectangle(0, y, self.width, self._s(20))
        self.display.set_pen(self.GREEN if live else self.RED)
        self.display.circle(self._s(12), y + self._s(10), max(2, self._s(4)))
        self.display.set_pen(self.LABEL)
        self.text.draw(status, self._s(22), y + self._s(5), self._s(11))
