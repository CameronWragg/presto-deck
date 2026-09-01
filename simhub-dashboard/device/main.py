"""Presto Deck - a SimHub speed/RPM dashboard for the Pimoroni Presto.

Copy the contents of device/ to the root of your Presto (plus a secrets.py
with your WiFi details) and reset the board.

Telemetry arrives as ASCII lines over WiFi (TCP or UDP) or, optionally, the
USB serial port. See simhub/README.md for the SimHub side.
"""

import gc
import time

from presto import Presto

import config
from dashboard import Dashboard
from netlink import LineLink
from telemetry import Telemetry

FRAME_MS = max(10, 1000 // config.TARGET_FPS)
LED_COUNT = 7


def connect_wifi(presto, dash):
    """Returns our IP address, or None if we couldn't get on the network."""
    dash.splash("PRESTO DECK", "connecting to wifi")
    try:
        if presto.connect():
            return presto.wifi.ipv4
    except Exception as error:  # noqa: BLE001 - no secrets.py, bad password, no AP
        print("WiFi failed:", error)
    return None


def update_leds(presto, dash, tel, live, now_ms, last):
    """Mirror the rev bar onto the ambient LEDs. Returns the new state."""
    if not live:
        state = [(0, 0, 0)] * LED_COUNT
    else:
        segments = dash.segment_colours(tel.rev_fraction, now_ms)
        state = []
        for index in range(LED_COUNT):
            # Sample the (wider) rev bar evenly across the 7 LEDs.
            lit, _pen = segments[int(index * len(segments) / LED_COUNT)]
            position = (index + 1) / LED_COUNT
            if not lit:
                state.append((0, 0, 0))
            elif tel.shifting and (now_ms // 60) % 2 == 0:
                state.append((0, 90, 255))
            elif position > 0.85:
                state.append((255, 0, 0))
            elif position > 0.60:
                state.append((255, 110, 0))
            else:
                state.append((0, 200, 60))

    if state != last:
        for index, (red, green, blue) in enumerate(state):
            presto.set_led_rgb(index, red, green, blue)
    return state


def main():
    presto = Presto(full_res=config.FULL_RES)
    presto.set_backlight(config.BACKLIGHT)

    dash = Dashboard(presto, config.VECTOR_FONT, config.SHIFT_START, config.SHIFT_FLASH)
    tel = Telemetry(config.DEFAULT_MAX_RPM, config.SHIFT_START, config.SHIFT_FLASH)

    ip = connect_wifi(presto, dash)
    link = LineLink(config.TCP_PORT, config.UDP_PORT, config.ENABLE_USB_SERIAL)
    print("listening on", link.describe(), "as", ip)
    if link.errors:
        print("link errors:", link.errors)

    dash.splash(ip or "NO WIFI", "listening on " + link.describe())
    time.sleep(1)

    units = config.UNITS
    demo = None
    demo_tel = None
    leds = None
    was_touched = False
    frames = 0
    fps = 0
    fps_mark = time.ticks_ms()
    last_frame = time.ticks_ms()

    while True:
        now = time.ticks_ms()

        for line in link.poll():
            tel.update(line, now)

        # Demo telemetry is kept in its own state so real telemetry, when it
        # arrives, takes over immediately.
        live = tel.is_live(now, config.STALE_MS)
        view = tel
        if live:
            demo = None
        elif config.DEMO_WHEN_IDLE:
            if demo is None:
                from demo import DemoCar

                demo = DemoCar()
                demo_tel = Telemetry(
                    config.DEFAULT_MAX_RPM, config.SHIFT_START, config.SHIFT_FLASH
                )
            demo_tel.update(demo.step(time.ticks_diff(now, last_frame)), now)
            view = demo_tel

        # Tap anywhere to swap between mph and km/h.
        touched = presto.touch_a.touched
        if touched and not was_touched:
            units = "kmh" if units == "mph" else "mph"
        was_touched = touched

        if demo is not None:
            status = "DEMO - waiting for simhub"
        elif live:
            status = "SIMHUB {} fps".format(fps)
        else:
            status = "{} {}".format(ip or "no wifi", link.describe())

        showing = live or demo is not None
        dash.render(view, units, showing, status, now)

        if config.AMBIENT_REV_LIGHTS:
            leds = update_leds(presto, dash, view, showing, now, leds)

        frames += 1
        if time.ticks_diff(now, fps_mark) >= 1000:
            fps = frames
            frames = 0
            fps_mark = now
            gc.collect()

        last_frame = now
        spare = FRAME_MS - time.ticks_diff(time.ticks_ms(), now)
        if spare > 0:
            time.sleep_ms(spare)


main()
