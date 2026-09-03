"""The OpenSky Network feed, turned into something a radar screen can draw.

One GET of /states/all returns a timestamp and an array of state vectors:

    {"time": 1788359476,
     "states": [["4068f5", "EXS216  ", "United Kingdom", 1788359475,
                 1788359476, -1.4052, 53.6721, 3817.62, false, 133.14,
                 323.48, -5.53, null, 3954.78, "6634", false, 0], ...]}

Each vector is a fixed list, not an object, so the fields are read by index -
see the constants below, which follow the order in the API documentation.
Anything the aircraft is not transmitting arrives as null, and plenty does:
aircraft on the ground routinely have no barometric altitude, and about a
third of any sample has no squawk. Nothing here turns a null into a zero.

OpenSky reports in metric units and gives no distance or bearing from a
query point, so this module converts to the feet and knots aviation reads
in, and works out range and bearing itself with geo.

Plain Python, so it runs under CPython too - see tests/test_flights.py.
"""

import geo

# Index of each field within a state vector.
ICAO24 = 0
CALLSIGN = 1
ORIGIN_COUNTRY = 2
TIME_POSITION = 3
LAST_CONTACT = 4
LONGITUDE = 5
LATITUDE = 6
BARO_ALTITUDE = 7
ON_GROUND = 8
VELOCITY = 9
TRUE_TRACK = 10
VERTICAL_RATE = 11
SENSORS = 12
GEO_ALTITUDE = 13
SQUAWK = 14
SPI = 15
POSITION_SOURCE = 16
CATEGORY = 17  # only present when the query asked for extended=1

VECTOR_LENGTH = 17  # everything up to and including position_source

METRES_TO_FEET = 3.280840
MS_TO_KNOTS = 1.943844
MS_TO_FEET_PER_MINUTE = 196.8504

POSITION_SOURCES = ("ADS-B", "ASTERIX", "MLAT", "FLARM")

# Squawks that mean something is wrong: hijack, radio failure, mayday.
EMERGENCY_SQUAWKS = ("7500", "7600", "7700")


def _number(value):
    """A numeric field, or None if it is missing or not a number."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _text(value):
    """A string field, trimmed. Callsigns arrive padded to 8 characters."""
    if value is None:
        return ""
    return str(value).strip()


def _at(vector, index):
    """A field by index, tolerating a vector shorter than the spec."""
    if index < len(vector):
        return vector[index]
    return None


def group_digits(number):
    """1234567 -> "1,234,567". MicroPython has no "{:,}" format spec."""
    digits = str(int(abs(number)))
    parts = []
    while len(digits) > 3:
        parts.insert(0, digits[-3:])
        digits = digits[:-3]
    parts.insert(0, digits)
    return ("-" if number < 0 else "") + ",".join(parts)


class Aircraft:
    """One state vector, in the units the screen wants."""

    def __init__(self, vector, home=None, now=None):
        self.icao24 = _text(_at(vector, ICAO24)).lower()
        self.callsign = _text(_at(vector, CALLSIGN))
        self.origin_country = _text(_at(vector, ORIGIN_COUNTRY))
        self.squawk = _text(_at(vector, SQUAWK))
        self.on_ground = bool(_at(vector, ON_GROUND))
        self.spi = bool(_at(vector, SPI))

        source = _number(_at(vector, POSITION_SOURCE))
        self.position_source = (
            POSITION_SOURCES[int(source)]
            if source is not None and 0 <= int(source) < len(POSITION_SOURCES)
            else ""
        )

        self.latitude = _number(_at(vector, LATITUDE))
        self.longitude = _number(_at(vector, LONGITUDE))

        # Barometric is what ATC and every other tracker quotes; geometric is
        # the fallback, and both are metres on the wire.
        altitude = _number(_at(vector, BARO_ALTITUDE))
        if altitude is None:
            altitude = _number(_at(vector, GEO_ALTITUDE))
        if self.on_ground:
            # On the ground the altitude field is usually absent anyway, and
            # an aerodrome's elevation is not what the panel wants to show.
            self.altitude = 0.0
        else:
            self.altitude = None if altitude is None else altitude * METRES_TO_FEET

        speed = _number(_at(vector, VELOCITY))
        self.ground_speed = None if speed is None else speed * MS_TO_KNOTS

        self.track = _number(_at(vector, TRUE_TRACK))

        climb = _number(_at(vector, VERTICAL_RATE))
        self.vertical_rate = None if climb is None else climb * MS_TO_FEET_PER_MINUTE

        # How stale the position is. OpenSky keeps an aircraft in the feed for
        # a while after its last message, so this is what separates a live
        # contact from one frozen where it was last heard.
        position_time = _number(_at(vector, TIME_POSITION))
        self.position_age = (
            None if position_time is None or now is None else max(0.0, now - position_time)
        )

        # OpenSky answers with a box and no ranges, so we work them out.
        self.distance = None
        self.bearing = None
        if home and self.located:
            self.distance = geo.distance_nm(home[0], home[1], self.latitude, self.longitude)
            self.bearing = geo.bearing_deg(home[0], home[1], self.latitude, self.longitude)

    # -- derived state -------------------------------------------------------

    @property
    def located(self):
        """True when we know where it is well enough to plot it."""
        return self.latitude is not None and self.longitude is not None

    @property
    def plottable(self):
        return self.located and self.distance is not None and self.bearing is not None

    @property
    def urgent(self):
        return self.squawk in EMERGENCY_SQUAWKS

    @property
    def climbing(self):
        return self.vertical_rate is not None and self.vertical_rate > 200

    @property
    def descending(self):
        return self.vertical_rate is not None and self.vertical_rate < -200

    # -- display -------------------------------------------------------------

    def label(self):
        """Callsign, falling back to the Mode S address.

        OpenSky carries no registration or type - its aircraft metadata
        endpoint is gone - so there is nothing between the two.
        """
        return self.callsign or self.icao24.upper() or "UNKNOWN"

    def altitude_text(self):
        if self.on_ground:
            return "ON GROUND"
        if self.altitude is None:
            return "--"
        return group_digits(self.altitude) + " ft"

    def speed_text(self):
        if self.ground_speed is None:
            return "--"
        return "{:.0f} kt".format(self.ground_speed)

    def distance_text(self, units="nm"):
        if self.distance is None:
            return "--"
        value = geo.convert(self.distance, units)
        # Sub-10 gets a decimal: the difference between 2 and 2.4 miles
        # overhead is worth seeing, the difference between 40 and 40.4 is not.
        return ("{:.1f}" if value < 10 else "{:.0f}").format(value)

    def bearing_text(self):
        if self.bearing is None:
            return "--"
        return "{} {:03.0f}".format(geo.compass_point(self.bearing), self.bearing % 360)

    def trend_text(self):
        if self.on_ground:
            return ""
        if self.climbing:
            return "climbing"
        if self.descending:
            return "descending"
        if self.vertical_rate is None:
            return ""
        return "level"

    def origin_text(self):
        """Country of registration, which is all the identity OpenSky gives."""
        return self.origin_country


def parse(payload, home=None, limit=None, radius=None, max_age=None,
          include_ground=False):
    """The `states` array as Aircraft, nearest first.

    Contacts with no position are dropped: there is nowhere to draw them and
    no distance to rank them by. `radius` trims the box back to the circle
    that was actually asked for, and `max_age` discards positions too stale
    to still mean anything.

    Aircraft on the ground are left out by default. An airport inside the
    circle otherwise contributes a dozen taxiing contacts that pile into one
    unreadable clump, and none of them is flying over anybody.
    """
    if not isinstance(payload, dict):
        return []

    now = _number(payload.get("time"))
    aircraft = []
    for vector in payload.get("states") or ():
        if not isinstance(vector, (list, tuple)):
            continue
        contact = Aircraft(vector, home, now)
        if not contact.plottable:
            continue
        if contact.on_ground and not include_ground:
            continue
        if radius is not None and contact.distance > radius:
            continue
        if (
            max_age is not None
            and contact.position_age is not None
            and contact.position_age > max_age
        ):
            continue
        aircraft.append(contact)

    aircraft.sort(key=lambda contact: contact.distance)
    if limit is not None and len(aircraft) > limit:
        del aircraft[limit:]
    return aircraft


def response_error(payload):
    """The feed's own complaint, or "" when the response looks usable.

    A healthy response always carries a `states` key, even when it is null
    for an empty sky.
    """
    if not isinstance(payload, dict):
        return "bad response"
    for key in ("error", "message", "error_description"):
        problem = _text(payload.get(key))
        if problem:
            return problem
    if "states" not in payload:
        return "unexpected response"
    return ""
