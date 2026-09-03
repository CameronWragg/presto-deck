"""Presto Deck - a live flight tracker for the Pimoroni Presto.

Shows the aircraft currently over your patch of sky on a north-up radar
scope, with the closest one written out along the bottom of the screen.

Copy the contents of device/ to the root of your Presto (plus a secrets.py
with your WiFi details) and reset the board. It finds where it is from your
public IP, then asks the OpenSky Network what is overhead - as often as the
day's remaining credit allowance allows, and no faster than REFRESH_SECONDS.

Tap the screen to step through the other aircraft on the scope; the next
refresh puts you back on the closest one.
"""

import gc
import time

from presto import Presto

import config
import flights
import geo
import netapi
from radar import Radar

FRAME_MS = max(20, 1000 // config.TARGET_FPS)
LED_COUNT = 7


class Tracker:
    """Everything the screen needs to know, and the polling that fills it."""

    def __init__(self):
        self.home = None  # (latitude, longitude)
        self.place = ""
        self.aircraft = []
        self.selected = 0

        self.status = "starting"
        self.level = "warn"
        self.demo = None

        self.tokens = netapi.TokenSource(
            config.OPENSKY_TOKEN_URL,
            config.OPENSKY_CLIENT_ID,
            config.OPENSKY_CLIENT_SECRET,
            config.REQUEST_TIMEOUT,
        )
        # Credits left in today's allowance, and what one request costs.
        # Both come from the feed rather than being assumed.
        self.credits = None
        self.cost = None
        self.low_credits = self.tokens.daily_credits // 5

        self.interval_ms = max(
            config.MIN_REFRESH_SECONDS, config.REFRESH_SECONDS
        ) * 1000
        self.backoff_ms = self.interval_ms
        # How long the wait we are currently counting down actually is, which
        # is not backoff_ms: that has already doubled ready for the next one.
        self.wait_ms = self.interval_ms
        self.next_due = time.ticks_ms()
        self.last_success = None

    # -- location ------------------------------------------------------------

    def locate(self):
        """Fix our position: the config if it is set, the IP lookup if not.

        Returns the (latitude, longitude) it settled on, or None.
        """
        if config.LATITUDE is not None and config.LONGITUDE is not None:
            self.home = (config.LATITUDE, config.LONGITUDE)
            self.place = config.LOCATION_NAME or "{:.2f}, {:.2f}".format(*self.home)
            return self.home

        try:
            latitude, longitude, city = netapi.locate(
                config.LOCATION_URL, config.REQUEST_TIMEOUT
            )
        except netapi.ApiError as error:
            print("location lookup failed:", error)
            self.status = "no location"
            self.level = "error"
            return None

        self.home = (latitude, longitude)
        self.place = config.LOCATION_NAME or city or "{:.2f}, {:.2f}".format(
            latitude, longitude
        )
        return self.home

    # -- the feed ------------------------------------------------------------

    def refresh(self, now):
        """One request. Schedules the next one either way."""
        home = self.home or self.locate()
        if home is None:
            self._failed(now)
            return

        if self.cost is None:
            box = geo.bounding_box(home[0], home[1], config.RADIUS_NM)
            self.cost = netapi.credit_cost(geo.box_area(box))
            print("each request costs {} credit(s)".format(self.cost))

        try:
            payload, credits = netapi.fetch_states(
                config.OPENSKY_BASE,
                home[0],
                home[1],
                config.RADIUS_NM,
                self.tokens.headers(now),
                config.REQUEST_TIMEOUT,
            )
        except netapi.ApiError as error:
            print("feed:", error)
            self.status = str(error)
            if error.status == 401:
                # The token has aged out, or the credentials are wrong. Drop
                # it either way, so the next attempt fetches a fresh one.
                self.tokens.forget()
            self._failed(now)
            return

        if credits is not None:
            self.credits = credits

        error = flights.response_error(payload)
        if error:
            print("feed:", error)
            self.status = error
            self._failed(now)
            return

        self.aircraft = flights.parse(
            payload,
            home,
            config.MAX_AIRCRAFT,
            config.RADIUS_NM,
            config.MAX_POSITION_AGE_SECONDS,
            config.SHOW_GROUND_TRAFFIC,
        )
        # Back to the closest aircraft on every refresh: the panel is meant
        # to answer "what is over me right now" without being touched.
        self.selected = 0
        self.demo = None
        self.status = ""
        self.level = "ok"
        self.last_success = now
        self.wait_ms = self.pace()
        self.backoff_ms = self.wait_ms
        self.next_due = time.ticks_add(now, self.wait_ms)
        # One line per refresh, so a serial console shows what the screen is
        # showing. The failure paths already print; staying silent on success
        # makes the quiet case indistinguishable from a wedged board.
        print("{} aircraft, {} credits left, next in {}s".format(
            len(self.aircraft), self.credits, self.wait_ms // 1000))
        gc.collect()

    def pace(self):
        """How long to wait before the next request, in milliseconds.

        OpenSky's allowance is a daily budget and every response says what is
        left of it, so rather than trusting a configured interval to fit, we
        spread what remains over a further 24 hours. That is deliberately
        pessimistic - the allowance resets well before then - but it needs no
        clock on a board that has never synchronised one, and it cannot spend
        tomorrow's credits today. Anonymously it settles around 3.5 minutes;
        with an account, on the configured interval.
        """
        if not config.ADAPTIVE_REFRESH or self.credits is None or self.cost is None:
            return self.interval_ms
        if self.credits <= 0:
            return config.MAX_BACKOFF_SECONDS * 1000
        return max(self.interval_ms, 86400 * 1000 * self.cost // self.credits)

    def _failed(self, now):
        """Back off, and fall back to the demo sky if there is nothing else.

        Doubling the wait keeps a rejected key or a feed outage from turning
        into a request every thirty seconds for as long as the board is on.
        """
        self.level = "error"
        self.wait_ms = self.backoff_ms
        self.next_due = time.ticks_add(now, self.wait_ms)
        self.backoff_ms = min(self.backoff_ms * 2, config.MAX_BACKOFF_SECONDS * 1000)

        if self.last_success is not None:
            # We have real aircraft on screen. Leave them there, stale, and
            # let the status bar say why they are not moving.
            return
        if config.DEMO_WHEN_UNAVAILABLE and self.demo is None:
            from demo import DEFAULT_LATITUDE, DEFAULT_LONGITUDE, DemoSky

            latitude, longitude = self.home or (DEFAULT_LATITUDE, DEFAULT_LONGITUDE)
            self.demo = DemoSky(latitude, longitude, config.RADIUS_NM)

    def step_demo(self, delta_ms):
        if self.demo is None:
            return
        payload = self.demo.step(delta_ms)
        self.aircraft = flights.parse(
            payload,
            self.home,
            config.MAX_AIRCRAFT,
            config.RADIUS_NM,
            config.MAX_POSITION_AGE_SECONDS,
            config.SHOW_GROUND_TRAFFIC,
        )
        if self.selected >= len(self.aircraft):
            self.selected = 0

    # -- view ----------------------------------------------------------------

    def progress(self, now):
        """0.0 - 1.0 towards the next request, for the countdown ring."""
        remaining = time.ticks_diff(self.next_due, now)
        if self.wait_ms <= 0:
            return 1.0
        return min(1.0, max(0.0, 1.0 - remaining / self.wait_ms))

    def banner(self, now):
        """(status text, level) for the top bar."""
        if self.demo is not None:
            return "DEMO - " + (self.status or "no feed"), "warn"
        if self.status:
            return self.status, self.level
        if self.last_success is None:
            return "waiting for feed", "warn"
        if self.credits is not None and self.credits <= self.low_credits:
            # Worth saying out loud: the interval is quietly stretching to
            # make what is left last the day.
            return "{} credits left".format(self.credits), "warn"
        age = time.ticks_diff(now, self.last_success) // 1000
        if age > config.REFRESH_SECONDS * 3:
            return "{}s old".format(age), "warn"
        return "", "ok"

    def cycle(self):
        """Tap: step to the next aircraft out, wrapping to the closest."""
        if self.aircraft:
            self.selected = (self.selected + 1) % len(self.aircraft)


def update_leds(presto, view, tracker, last):
    """Tint the ambient LEDs with the closest aircraft's altitude colour.

    Brightness follows how close it is, so the unit glows as something
    passes overhead. Returns the new state so we only push on a change.
    """
    if not tracker.aircraft:
        state = (0, 0, 0)
    else:
        contact = tracker.aircraft[0]
        red, green, blue = view.altitude_rgb(contact)
        near = 1.0 - min(contact.distance / max(config.RADIUS_NM, 1), 1.0)
        level = 0.12 + 0.88 * near * near
        state = (int(red * level), int(green * level), int(blue * level))

    if state != last:
        for index in range(LED_COUNT):
            presto.set_led_rgb(index, state[0], state[1], state[2])
    return state


def connect_wifi(presto, view):
    """Returns our IP address, or None if we couldn't get on the network."""
    view.splash("FLIGHT TRACKER", "connecting to wifi")
    try:
        if presto.connect():
            return presto.wifi.ipv4()
    except Exception as error:  # noqa: BLE001 - no secrets.py, bad password, no AP
        print("WiFi failed:", error)
    return None


def main():
    presto = Presto(full_res=config.FULL_RES)
    presto.set_backlight(config.BACKLIGHT)

    view = Radar(presto, config.VECTOR_FONT, config.DISTANCE_UNITS)
    tracker = Tracker()

    ip = connect_wifi(presto, view)
    if ip is None:
        tracker.status = "no wifi"
        tracker.level = "error"
    else:
        view.splash("FLIGHT TRACKER", "finding your location")
        tracker.locate()

    if tracker.home:
        print("centred on {:.4f}, {:.4f} ({})".format(
            tracker.home[0], tracker.home[1], tracker.place or "unnamed"))
    view.splash("FLIGHT TRACKER", tracker.place or tracker.status or "scanning")
    time.sleep(1)

    leds = None
    was_touched = False
    last_frame = time.ticks_ms()

    while True:
        now = time.ticks_ms()
        delta = time.ticks_diff(now, last_frame)
        last_frame = now

        if time.ticks_diff(now, tracker.next_due) >= 0:
            # Say so before blocking on the request, so a slow reply looks
            # like an update rather than a freeze.
            status, level = tracker.banner(now)
            view.render(tracker.aircraft, tracker.selected, tracker.place,
                        status or "updating", level, 1.0, config.RADIUS_NM)
            tracker.refresh(now)
            now = time.ticks_ms()
            last_frame = now

        if tracker.demo is not None:
            tracker.step_demo(delta)

        touched = presto.touch_a.touched
        if touched and not was_touched:
            tracker.cycle()
        was_touched = touched

        status, level = tracker.banner(now)
        view.render(tracker.aircraft, tracker.selected, tracker.place, status,
                    level, tracker.progress(now), config.RADIUS_NM)

        if config.AMBIENT_LEDS:
            leds = update_leds(presto, view, tracker, leds)

        spare = FRAME_MS - time.ticks_diff(time.ticks_ms(), now)
        if spare > 0:
            time.sleep_ms(spare)


main()
