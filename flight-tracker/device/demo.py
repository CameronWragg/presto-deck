"""Synthetic traffic, so the radar has something to show with no feed.

Emits the same state vectors OpenSky returns - metric units, fields by
position, callsigns padded to eight characters - so the demo goes through
exactly the same parsing and drawing path as real data. If it looks right
here, the only thing left to get wrong is the network.

Handy when the daily credit allowance is spent, when the WiFi is down, and
for working on the layout at a desk with no sky worth watching.
"""

import geo

# Somewhere to centre the demo when we never found out where we are.
# Central London: busy enough that a 30 NM circle is a realistic picture.
DEFAULT_LATITUDE = 51.5074
DEFAULT_LONGITUDE = -0.1278

# OpenSky reports metric; the numbers below are in the units a pilot would
# use, and get converted on the way out just as the real feed's are on the
# way in.
FEET_TO_METRES = 0.3048
KNOTS_TO_MS = 0.514444
FEET_PER_MINUTE_TO_MS = 0.00508

# callsign, country of registration
FLEET = (
    ("BAW117", "United Kingdom"),
    ("EZY83DK", "United Kingdom"),
    ("RYR14XG", "Ireland"),
    ("VIR25F", "United Kingdom"),
    ("KLM89T", "Netherlands"),
    ("UAE7", "United Arab Emirates"),
    ("NJE461R", "Portugal"),
    ("POLICE9", "United Kingdom"),
)


class DemoSky:
    """A handful of aircraft flying steady arcs around the home point."""

    def __init__(self, latitude, longitude, radius_nm=30.0, count=6):
        self.latitude = latitude
        self.longitude = longitude
        self.radius = radius_nm
        self.elapsed_ms = 0

        self.traffic = []
        count = min(count, len(FLEET))
        for index in range(count):
            callsign, country = FLEET[index]
            self.traffic.append(
                {
                    "callsign": callsign,
                    "country": country,
                    # Spread them round the circle at different ranges and
                    # heights so the altitude colours and the range rings
                    # both get exercised.
                    "bearing": 360.0 * index / count,
                    "range": radius_nm * (0.18 + 0.72 * ((index * 3) % count) / count),
                    "altitude": 1500 + index * 5500,
                    "speed": 180 + index * 45,
                    # Alternate direction so they do not orbit in lockstep.
                    "rate": (0.9 + 0.35 * index) * (1 if index % 2 else -1),
                }
            )

    def step(self, delta_ms):
        """Advance the traffic and return a /states/all response."""
        self.elapsed_ms += max(0, delta_ms)
        seconds = self.elapsed_ms / 1000.0
        now = int(seconds)

        states = []
        for index, plane in enumerate(self.traffic):
            bearing = (plane["bearing"] + plane["rate"] * seconds) % 360.0
            # A slow breathe in and out of the centre, so the closest
            # aircraft - and the panel at the bottom - keeps changing.
            wobble = 1.0 + 0.22 * _wave(seconds / 40.0 + index * 0.37)
            distance = min(self.radius, plane["range"] * wobble)
            latitude, longitude = geo.project(
                self.latitude, self.longitude, bearing, distance
            )
            # Flying an arc around us, so the track is tangential.
            track = (bearing + (90.0 if plane["rate"] > 0 else -90.0)) % 360.0

            # An integer offset would put every aircraft at the same point of
            # a period-1 wave, so the whole fleet would climb and descend
            # together. Nudge each one by a fraction of a cycle instead.
            phase = seconds / 25.0 + index * 0.37
            altitude = plane["altitude"] + 900 * _wave(phase)
            # _wave falls over the first half of its cycle and rises over the
            # second, so the reported climb rate agrees with the altitude.
            climb = -700 if (phase % 1.0) < 0.5 else 700

            states.append([
                "{:06x}".format(0x400000 + index * 0x1D3B),  # icao24
                plane["callsign"] + "  ",                    # callsign, padded
                plane["country"],                            # origin_country
                now,                                         # time_position
                now,                                         # last_contact
                longitude,
                latitude,
                altitude * FEET_TO_METRES,                   # baro_altitude, m
                False,                                       # on_ground
                plane["speed"] * KNOTS_TO_MS,                # velocity, m/s
                track,                                       # true_track
                climb * FEET_PER_MINUTE_TO_MS,               # vertical_rate, m/s
                None,                                        # sensors
                (altitude + 300) * FEET_TO_METRES,           # geo_altitude, m
                "{:04d}".format(1000 + index * 111),         # squawk
                False,                                       # spi
                0,                                           # position_source
            ])

        return {"time": now, "states": states}


def _wave(turns):
    """A -1..1 triangle wave. Cheaper than sin, and nobody can tell."""
    position = turns % 1.0
    return 4.0 * abs(position - 0.5) - 1.0
