"""Screen layout for the flight tracker.

A plan-position scope with you at the centre, north up, ringed by a countdown
that fills as the next refresh comes due, and a panel along the bottom
holding whichever aircraft is selected - the closest one, until you tap.

Everything is laid out from display.get_bounds() against a 240x240 design
grid, so the same code fills the screen in both normal and full_res mode.
"""

import math

import geo

BASE = 240  # the design grid this layout was drawn on

STATUS_HEIGHT = 16  # top bar
PANEL_HEIGHT = 58  # bottom readout
# The scope has to leave room for the cardinal letters between the status bar
# and the panel: with the centre 83 pixels from each, a letter centred at
# SCOPE_RADIUS + CARDINAL_GAP must keep its half-height inside that.
SCOPE_RADIUS = 66
CARDINAL_GAP = 12
COUNTDOWN_GAP = 4
RANGE_RINGS = 3
COUNTDOWN_TICKS = 36

# Altitude bands, low to high: the colour scheme every ADS-B map uses, so a
# glance tells you the airliners from the helicopter over the ring road.
# (ceiling in feet, (r, g, b))
ALTITUDE_BANDS = (
    (4000, (255, 85, 60)),
    (8000, (255, 155, 45)),
    (14000, (245, 215, 70)),
    (22000, (115, 220, 95)),
    (30000, (70, 200, 235)),
    (1000000, (155, 135, 255)),
)


class TextRenderer:
    """Text via PicoVector when a font is available, bitmap font otherwise."""

    def __init__(self, display, font_path=None):
        self.display = display
        self.vector = None
        self.transform = None
        self._wrap = display.get_bounds()[0]
        display.set_font("bitmap8")
        if font_path:
            self._try_vector(font_path)

    def _try_vector(self, font_path):
        try:
            from picovector import ANTIALIAS_X4, PicoVector, Transform

            vector = PicoVector(self.display)
            vector.set_antialiasing(ANTIALIAS_X4)
            # PicoVector keeps only a raw pointer to the transform, so the
            # object has to outlive this call. Passing Transform() inline
            # leaves it unreferenced, and once the GC takes it PicoVector
            # reads freed memory - which shows up as text drawing that
            # intermittently hangs the board or corrupts unrelated objects,
            # not as an error here. Every Presto example binds it to a name;
            # so do we.
            self.transform = Transform()
            vector.set_transform(self.transform)
            vector.set_font(font_path, 24)
            self.vector = vector
        except Exception:  # noqa: BLE001 - no font on device, bitmap is fine
            self.vector = None

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

    def fit(self, text, size, width):
        """`text` shortened with an ellipsis until it fits inside `width`."""
        if not text or self.measure(text, size)[0] <= width:
            return text
        while text and self.measure(text + "...", size)[0] > width:
            text = text[:-1]
        return text + "..." if text else ""

    def draw(self, text, x, y, size, align="left"):
        """Draw `text` with its top-left/top-centre/top-right at (x, y)."""
        width, height = self.measure(text, size)
        if align == "centre":
            x -= width // 2
        elif align == "right":
            x -= width
        self._draw_at(text, int(x), int(y), size)
        return width, height

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


class Radar:
    def __init__(self, presto, font_path=None, units="nm"):
        self.presto = presto
        self.display = presto.display
        self.width, self.height = self.display.get_bounds()
        self.scale = self.width / BASE
        self.units = units
        self.text = TextRenderer(self.display, font_path)

        create = self.display.create_pen
        self.BG = create(6, 8, 12)
        self.PANEL = create(20, 24, 32)
        self.RING = create(32, 48, 56)
        self.RING_BRIGHT = create(58, 92, 104)
        self.DIM = create(80, 90, 105)
        self.LABEL = create(135, 148, 165)
        self.WHITE = create(240, 245, 255)
        self.GREEN = create(0, 220, 110)
        self.AMBER = create(255, 176, 0)
        self.RED = create(255, 60, 55)
        self.HOME = create(0, 230, 200)
        self.SELECT = create(255, 255, 255)

        self.band_pens = [(ceiling, create(*rgb)) for ceiling, rgb in ALTITUDE_BANDS]
        self.GROUND = create(150, 152, 160)

        # Scope geometry, on the design grid.
        self.centre_x = BASE // 2
        self.centre_y = STATUS_HEIGHT + (BASE - STATUS_HEIGHT - PANEL_HEIGHT) // 2

    def _s(self, value):
        """Scale a design-grid measurement to the real display."""
        return int(value * self.scale)

    # -- colour --------------------------------------------------------------

    def altitude_pen(self, aircraft):
        if aircraft.on_ground:
            return self.GROUND
        if aircraft.altitude is None:
            return self.DIM
        for ceiling, pen in self.band_pens:
            if aircraft.altitude < ceiling:
                return pen
        return self.band_pens[-1][1]

    def altitude_rgb(self, aircraft):
        """The same banding as raw channels, for the ambient LEDs."""
        if aircraft.on_ground:
            return (150, 152, 160)
        if aircraft.altitude is None:
            return (80, 90, 105)
        for ceiling, rgb in ALTITUDE_BANDS:
            if aircraft.altitude < ceiling:
                return rgb
        return ALTITUDE_BANDS[-1][1]

    # -- public --------------------------------------------------------------

    def splash(self, title, subtitle=""):
        self.display.set_pen(self.BG)
        self.display.clear()
        self.display.set_pen(self.WHITE)
        self.text.draw(title, self.width // 2, self._s(100), self._s(18), "centre")
        if subtitle:
            self.display.set_pen(self.LABEL)
            self.text.draw(subtitle, self.width // 2, self._s(126), self._s(11), "centre")
        self.presto.update()

    def render(self, aircraft, selected, place, status, level, progress, range_nm):
        """Draw a whole frame.

        `aircraft` is nearest-first, `selected` indexes it, `progress` is
        0.0-1.0 towards the next refresh and `level` tints the status dot.
        """
        self.display.set_pen(self.BG)
        self.display.clear()

        self._scope(range_nm)
        self._countdown(progress)
        for index, contact in enumerate(aircraft):
            if index != selected:
                self._contact(contact, range_nm, False)
        # The selected contact goes on top of the rest.
        if 0 <= selected < len(aircraft):
            self._contact(aircraft[selected], range_nm, True)

        self._status_bar(place, status, level, len(aircraft))
        self._panel(aircraft, selected)
        self.presto.update()

    # -- scope ---------------------------------------------------------------

    def _scope(self, range_nm):
        centre_x = self._s(self.centre_x)
        centre_y = self._s(self.centre_y)

        self.display.set_pen(self.RING)
        for ring in range(1, RANGE_RINGS + 1):
            radius = self._s(SCOPE_RADIUS * ring / RANGE_RINGS)
            self._ring(centre_x, centre_y, radius)

        # Cardinal ticks, north picked out so the orientation is unmistakable.
        for index, name in enumerate(("N", "E", "S", "W")):
            angle = math.radians(index * 90)
            outer = self._s(SCOPE_RADIUS + CARDINAL_GAP)
            x = centre_x + int(outer * math.sin(angle))
            y = centre_y - int(outer * math.cos(angle))
            self.display.set_pen(self.LABEL if name == "N" else self.DIM)
            self.text.draw(name, x, y - self._s(4), self._s(8), "centre")

        # Range labels ride the north-east diagonal, clear of the cardinal
        # letters above them and of the panel below. The outer ring carries
        # the unit, so the scale is never a guess and never repeated.
        self.display.set_pen(self.DIM)
        label_size = self._s(7)
        diagonal = math.sqrt(0.5)
        for ring in range(1, RANGE_RINGS + 1):
            radius = SCOPE_RADIUS * ring / RANGE_RINGS
            value = geo.convert(range_nm * ring / RANGE_RINGS, self.units)
            label = "{:.0f}".format(value)
            if ring == RANGE_RINGS:
                label += " " + geo.unit_label(self.units)
            self.text.draw(
                label,
                centre_x + self._s(radius * diagonal + 2),
                centre_y - self._s(radius * diagonal + 1) - label_size,
                label_size,
            )

        # Us.
        self.display.set_pen(self.HOME)
        self.display.circle(centre_x, centre_y, max(2, self._s(2)))

    def _ring(self, centre_x, centre_y, radius):
        """A circle outline, drawn as a ring of short chords.

        PicoGraphics only fills circles, and stacking two filled ones would
        paint over the contacts already on the scope.
        """
        steps = max(24, radius // 2)
        previous = None
        for step in range(steps + 1):
            angle = 2 * math.pi * step / steps
            point = (
                centre_x + int(radius * math.sin(angle)),
                centre_y - int(radius * math.cos(angle)),
            )
            if previous is not None:
                self.display.line(previous[0], previous[1], point[0], point[1])
            previous = point

    def _countdown(self, progress):
        """Tick marks around the bezel, filling as the next refresh nears."""
        centre_x = self._s(self.centre_x)
        centre_y = self._s(self.centre_y)
        radius = self._s(SCOPE_RADIUS + COUNTDOWN_GAP)
        lit = int(min(max(progress, 0.0), 1.0) * COUNTDOWN_TICKS + 0.5)
        size = max(1, self._s(1))

        for index in range(COUNTDOWN_TICKS):
            angle = 2 * math.pi * index / COUNTDOWN_TICKS
            x = centre_x + int(radius * math.sin(angle))
            y = centre_y - int(radius * math.cos(angle))
            self.display.set_pen(self.RING_BRIGHT if index < lit else self.RING)
            self.display.circle(x, y, size)

    def _contact(self, aircraft, range_nm, selected):
        offset_x, offset_y = geo.radar_offset(
            aircraft.bearing, aircraft.distance, range_nm, SCOPE_RADIUS
        )
        x = self._s(self.centre_x + offset_x)
        y = self._s(self.centre_y + offset_y)

        if selected:
            self.display.set_pen(self.SELECT)
            self._brackets(x, y, self._s(8))
        if aircraft.urgent:
            self.display.set_pen(self.RED)
            self._brackets(x, y, self._s(11))

        self.display.set_pen(self.altitude_pen(aircraft))
        size = self._s(4.5)
        if aircraft.track is None:
            # Nothing to point it with, so a plain blip.
            self.display.circle(x, y, max(2, size // 2))
        else:
            self._arrow(x, y, aircraft.track, max(3, size))

        if selected:
            self.display.set_pen(self.WHITE)
            self.text.draw(aircraft.label(), x, y + self._s(8), self._s(8), "centre")

    def _brackets(self, x, y, half):
        """Corner ticks around a contact.

        A circle this small, rounded onto an integer grid, comes out looking
        like a cog at 240x240; four right angles stay crisp at both
        resolutions.
        """
        arm = max(2, int(half * 0.55))
        for step_x in (-1, 1):
            for step_y in (-1, 1):
                corner_x = x + step_x * half
                corner_y = y + step_y * half
                self.display.line(corner_x, corner_y, corner_x - step_x * arm, corner_y)
                self.display.line(corner_x, corner_y, corner_x, corner_y - step_y * arm)

    def _arrow(self, x, y, track, size):
        """A triangle pointing along `track`, degrees clockwise from north."""
        angle = math.radians(track)
        sin_t = math.sin(angle)
        cos_t = math.cos(angle)
        points = []
        # Nose, then the two trailing corners, on a north-pointing triangle.
        for point_x, point_y in ((0.0, -size), (-size * 0.62, size * 0.7),
                                 (size * 0.62, size * 0.7)):
            points.append(int(x + point_x * cos_t - point_y * sin_t))
            points.append(int(y + point_x * sin_t + point_y * cos_t))
        self.display.triangle(*points)

    # -- chrome --------------------------------------------------------------

    def _status_bar(self, place, status, level, count):
        height = self._s(STATUS_HEIGHT)
        self.display.set_pen(self.PANEL)
        self.display.rectangle(0, 0, self.width, height)

        dot = {"ok": self.GREEN, "warn": self.AMBER, "error": self.RED}.get(
            level, self.LABEL
        )
        self.display.set_pen(dot)
        self.display.circle(self._s(9), height // 2, max(2, self._s(3)))

        text_y = (height - self._s(8)) // 2
        right = "{} AC".format(count) if count else ""
        right_width = self.text.measure(right, self._s(8))[0] if right else 0

        left = place or status
        if place and status:
            left = "{}  ".format(place)
        available = self.width - self._s(18) - right_width - self._s(10)
        self.display.set_pen(self.WHITE if place else self.LABEL)
        used = self.text.draw(
            self.text.fit(left, self._s(8), available), self._s(16), text_y, self._s(8)
        )[0]

        if place and status:
            self.display.set_pen(self.LABEL)
            self.text.draw(
                self.text.fit(status, self._s(8), available - used),
                self._s(16) + used,
                text_y,
                self._s(8),
            )

        if right:
            self.display.set_pen(self.LABEL)
            self.text.draw(right, self.width - self._s(6), text_y, self._s(8), "right")

    def _panel(self, aircraft, selected):
        top = self.height - self._s(PANEL_HEIGHT)
        self.display.set_pen(self.PANEL)
        self.display.rectangle(0, top, self.width, self.height - top)

        if not aircraft or not (0 <= selected < len(aircraft)):
            self.display.set_pen(self.DIM)
            self.text.draw(
                "NO AIRCRAFT IN RANGE",
                self.width // 2,
                top + self._s(22),
                self._s(11),
                "centre",
            )
            return

        contact = aircraft[selected]
        left = self._s(8)
        right = self.width - self._s(8)

        # A stripe of the aircraft's altitude colour ties the panel to the
        # blip on the scope.
        self.display.set_pen(self.altitude_pen(contact))
        self.display.rectangle(0, top, max(2, self._s(3)), self.height - top)

        distance = contact.distance_text(self.units)
        unit = geo.unit_label(self.units)
        distance_size = self._s(17)
        unit_size = self._s(8)
        unit_width = self.text.measure(" " + unit, unit_size)[0]

        self.display.set_pen(self.WHITE)
        self.text.draw(
            distance, right - unit_width, top + self._s(5), distance_size, "right"
        )
        self.display.set_pen(self.LABEL)
        self.text.draw(" " + unit, right, top + self._s(11), unit_size, "right")

        distance_width = self.text.measure(distance, distance_size)[0] + unit_width
        self.display.set_pen(self.RED if contact.urgent else self.WHITE)
        self.text.draw(
            self.text.fit(
                contact.label(), self._s(19), self.width - left - distance_width - self._s(14)
            ),
            left,
            top + self._s(4),
            self._s(19),
        )

        detail = self._s(9)
        self.display.set_pen(self.LABEL)
        self.text.draw(
            self.text.fit(
                contact.origin_text() or "unknown origin",
                detail,
                self.width - left * 2 - self._s(52),
            ),
            left,
            top + self._s(27),
            detail,
        )
        self.text.draw(contact.bearing_text(), right, top + self._s(27), detail, "right")

        self.display.set_pen(self.altitude_pen(contact))
        altitude = contact.altitude_text()
        used = self.text.draw(altitude, left, top + self._s(41), detail)[0]

        # An emergency takes this slot over from the climb/descend note: a
        # 7700 squawk matters more than which way the aircraft is going, and
        # sharing the line would print the two on top of each other.
        if contact.urgent:
            note = ("squawk " + contact.squawk).upper()
            self.display.set_pen(self.RED)
        else:
            note = contact.trend_text()
            self.display.set_pen(self.DIM)
        if note:
            self.text.draw("  " + note, left + used, top + self._s(41), detail)

        self.display.set_pen(self.LABEL)
        self.text.draw(contact.speed_text(), right, top + self._s(41), detail, "right")
