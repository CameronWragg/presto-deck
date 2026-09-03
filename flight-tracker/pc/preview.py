#!/usr/bin/env python3
"""Draw the flight tracker's screen on your PC, without a Presto.

Runs the real device/radar.py against a stand-in for PicoGraphics that writes
SVG instead of pushing pixels, so you can see the layout - and prove it still
draws - without deploying anything.

    python pc/preview.py                       # demo traffic, 480x480
    python pc/preview.py --out screen.svg
    python pc/preview.py --payload capture.json --lat 53.35 --lon -1.48
    python pc/preview.py --state no-aircraft --state error

`--payload` takes a saved /states/all response - `pc/check_access.py --save`
writes one - so you can lay the screen out against the sky over your own house.

The device picks PicoVector up when a .af font is on the board; there is no
PicoVector here, so this previews the built-in bitmap font path. On the real
thing the text is smoother.
"""

import argparse
import json
import os
import sys
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "device"))

import demo as demo_module  # noqa: E402 - needs the path above
import flights  # noqa: E402
import radar as radar_module  # noqa: E402

# The bitmap8 font is 8 pixels tall per unit of scale, and its glyphs advance
# about six. Good enough that anything overflowing here overflows on the board.
GLYPH_ADVANCE = 6
GLYPH_HEIGHT = 8


class PreviewDisplay:
    """Enough of PicoGraphics to run radar.py, emitting SVG as it goes."""

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.elements = []
        self._pens = []
        self._pen = "#ffffff"
        self._font = "bitmap8"

    # -- state ---------------------------------------------------------------

    def get_bounds(self):
        return self.width, self.height

    def create_pen(self, red, green, blue):
        self._pens.append("#{:02x}{:02x}{:02x}".format(red, green, blue))
        return len(self._pens) - 1

    def set_pen(self, pen):
        self._pen = self._pens[pen]

    def set_font(self, font):
        self._font = font

    # -- drawing -------------------------------------------------------------

    def clear(self):
        self.elements.append(
            '<rect x="0" y="0" width="{}" height="{}" fill="{}"/>'.format(
                self.width, self.height, self._pen
            )
        )

    def rectangle(self, x, y, width, height):
        self.elements.append(
            '<rect x="{}" y="{}" width="{}" height="{}" fill="{}"/>'.format(
                x, y, width, height, self._pen
            )
        )

    def circle(self, x, y, radius):
        self.elements.append(
            '<circle cx="{}" cy="{}" r="{}" fill="{}"/>'.format(x, y, radius, self._pen)
        )

    def line(self, x1, y1, x2, y2, thickness=1):
        self.elements.append(
            '<line x1="{}" y1="{}" x2="{}" y2="{}" stroke="{}" '
            'stroke-width="{}" stroke-linecap="round"/>'.format(
                x1, y1, x2, y2, self._pen, thickness
            )
        )

    def triangle(self, x1, y1, x2, y2, x3, y3):
        self.elements.append(
            '<polygon points="{},{} {},{} {},{}" fill="{}"/>'.format(
                x1, y1, x2, y2, x3, y3, self._pen
            )
        )

    # These mirror PicoGraphics' signatures so radar.py can call them exactly
    # as it calls the real thing; the arguments it never passes are unused
    # here on purpose.
    def measure_text(self, text, scale=2, spacing=1, fixed_width=False):  # noqa: ARG002
        return int(len(text) * GLYPH_ADVANCE * scale)

    def text(self, text, x, y, wordwrap=-1, scale=2, angle=0,  # noqa: ARG002
             spacing=1, fixed_width=False):  # noqa: ARG002
        if not text:
            return
        # textLength pins the drawn string to exactly the width the layout
        # was measured against, so the preview cannot flatter itself.
        self.elements.append(
            '<text x="{}" y="{:.1f}" fill="{}" font-family="DejaVu Sans Mono,'
            'Menlo,Consolas,monospace" font-size="{}" textLength="{}" '
            'lengthAdjust="spacingAndGlyphs">{}</text>'.format(
                x,
                y + GLYPH_HEIGHT * scale * 0.82,
                self._pen,
                GLYPH_HEIGHT * scale,
                self.measure_text(text, scale),
                escape(text),
            )
        )

    # -- output --------------------------------------------------------------

    def svg(self):
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="{0}" height="{0}" '
            'viewBox="0 0 {0} {0}">\n{1}\n</svg>\n'.format(
                self.width, "\n".join(self.elements)
            )
        )


class PreviewPresto:
    """The handful of Presto methods radar.py touches."""

    def __init__(self, width, height):
        self.display = PreviewDisplay(width, height)

    def update(self):
        pass

    def set_backlight(self, brightness):
        pass

    def set_led_rgb(self, index, red, green, blue):
        pass


def load_aircraft(args):
    """The contacts to draw, and the point they are measured from."""
    home = (args.lat, args.lon)
    if args.payload:
        with open(args.payload) as handle:
            payload = json.load(handle)
    else:
        sky = demo_module.DemoSky(args.lat, args.lon, args.radius)
        payload = sky.step(args.time * 1000)
    aircraft = flights.parse(
        payload, home, args.max_aircraft, args.radius, args.max_age, args.ground
    )
    return aircraft, home


STATES = {
    "normal": ("Sheffield", "", "ok", 0.35),
    "demo": ("Sheffield", "DEMO - 403 - no API access", "warn", 0.6),
    "error": ("Sheffield", "403 - no API access", "error", 0.1),
    "stale": ("Sheffield", "184s old", "warn", 0.9),
    "no-aircraft": ("Sheffield", "", "ok", 0.5),
    "locating": ("", "no location", "error", 0.0),
    "emergency": ("Sheffield", "", "ok", 0.5),
}


def render(args, state):
    place, status, level, progress = STATES[state]
    aircraft, _home = load_aircraft(args)
    if state == "no-aircraft":
        aircraft = []
    if state == "locating":
        aircraft = []
    if state == "emergency" and aircraft:
        # Squawk 7700 on the nearest contact, to check the alert styling.
        aircraft[0].squawk = "7700"

    presto = PreviewPresto(args.size, args.size)
    view = radar_module.Radar(presto, None, args.units)
    view.render(aircraft, args.selected, place, status, level, progress, args.radius)
    return presto.display.svg(), aircraft


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", default="preview.svg",
                        help="output file; one per --state, suffixed")
    parser.add_argument("--size", type=int, default=480,
                        help="480 for full_res, 240 otherwise")
    parser.add_argument("--payload", help="a saved v2 response to draw instead of demo traffic")
    parser.add_argument("--lat", type=float, default=demo_module.DEFAULT_LATITUDE)
    parser.add_argument("--lon", type=float, default=demo_module.DEFAULT_LONGITUDE)
    parser.add_argument("--radius", type=float, default=30.0, help="range of the scope, NM")
    parser.add_argument("--units", default="nm", choices=("nm", "km", "mi"))
    parser.add_argument("--selected", type=int, default=0,
                        help="which aircraft the bottom panel shows")
    parser.add_argument("--max-aircraft", type=int, default=40)
    parser.add_argument("--ground", action="store_true",
                        help="include aircraft on the ground")
    parser.add_argument("--max-age", type=float, default=None,
                        help="drop positions older than this many seconds")
    parser.add_argument("--time", type=float, default=45.0,
                        help="seconds into the demo to draw")
    parser.add_argument("--state", action="append", choices=sorted(STATES),
                        help="screen state; repeatable (default: normal)")
    args = parser.parse_args()

    states = args.state or ["normal"]
    root, extension = os.path.splitext(args.out)
    extension = extension or ".svg"

    for state in states:
        svg, aircraft = render(args, state)
        path = args.out if len(states) == 1 else "{}-{}{}".format(root, state, extension)
        with open(path, "w") as handle:
            handle.write(svg)
        print("{}  ({} aircraft, {})".format(path, len(aircraft), state))


if __name__ == "__main__":
    main()
