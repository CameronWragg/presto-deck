"""Tests for the feed parsing, unit conversion and readout formatting.

    pytest tests

conftest.py puts the device modules on sys.path. The vectors below are real
responses from OpenSky's /states/all, kept verbatim: fields by position,
metric units, and null wherever an aircraft is not transmitting something.
"""

import pytest

import flights
import geo
from demo import DemoSky

HOME = (53.3548, -1.4839)

#          icao24   callsign      country          t_pos       last_contact
#          lon      lat      baro_m   ground  vel_ms  track   vrate_ms
#          sensors  geo_m    squawk  spi    source
AIRBORNE = ["4068f5", "EXS216  ", "United Kingdom", 1788359475, 1788359476,
            -1.4052, 53.6721, 3817.62, False, 133.14, 323.48, -5.53,
            None, 3954.78, "6634", False, 0]

# On the ground at Manchester: no altitude, no squawk, walking pace.
ON_GROUND = ["406752", "EZY52JX ", "United Kingdom", 1788359476, 1788359476,
             -2.2747, 53.3558, None, True, 5.4, 140.62, None,
             None, None, None, False, 0]

NOW = 1788359476


def placed(distance_nm, bearing_deg, home=HOME):
    """An AIRBORNE contact moved to an exact range and bearing from home."""
    latitude, longitude = geo.project(home[0], home[1], bearing_deg, distance_nm)
    vector = list(AIRBORNE)
    vector[flights.LATITUDE] = latitude
    vector[flights.LONGITUDE] = longitude
    return flights.Aircraft(vector, home, NOW)


def envelope(*states, **kwargs):
    return {"time": kwargs.get("time", NOW), "states": list(states)}


class TestUnitConversion:
    """OpenSky is metric; the screen is not."""

    def test_altitude_metres_to_feet(self):
        contact = flights.Aircraft(AIRBORNE, HOME, NOW)
        assert contact.altitude == pytest.approx(3817.62 * 3.280840)
        assert contact.altitude == pytest.approx(12525.0, abs=1.0)

    def test_speed_ms_to_knots(self):
        contact = flights.Aircraft(AIRBORNE, HOME, NOW)
        assert contact.ground_speed == pytest.approx(133.14 * 1.943844)
        assert contact.speed_text() == "259 kt"

    def test_vertical_rate_ms_to_feet_per_minute(self):
        contact = flights.Aircraft(AIRBORNE, HOME, NOW)
        assert contact.vertical_rate == pytest.approx(-5.53 * 196.8504)
        assert contact.descending
        assert contact.trend_text() == "descending"

    def test_geometric_altitude_is_the_fallback(self):
        vector = list(AIRBORNE)
        vector[flights.BARO_ALTITUDE] = None
        contact = flights.Aircraft(vector, HOME, NOW)
        assert contact.altitude == pytest.approx(3954.78 * 3.280840)


class TestFields:
    def test_reads_a_real_vector(self):
        contact = flights.Aircraft(AIRBORNE, HOME, NOW)
        assert contact.icao24 == "4068f5"
        assert contact.callsign == "EXS216"  # the padding is stripped
        assert contact.origin_country == "United Kingdom"
        assert contact.squawk == "6634"
        assert contact.track == pytest.approx(323.48)
        assert contact.position_source == "ADS-B"
        assert not contact.on_ground
        assert not contact.urgent

    def test_on_the_ground(self):
        contact = flights.Aircraft(ON_GROUND, HOME, NOW)
        assert contact.on_ground
        assert contact.altitude == 0
        assert contact.altitude_text() == "ON GROUND"
        assert contact.trend_text() == ""
        assert contact.squawk == ""

    def test_missing_altitude_is_none_not_zero(self):
        # Drawing 0 ft for an aircraft that is not reporting would be a lie.
        vector = list(AIRBORNE)
        vector[flights.BARO_ALTITUDE] = None
        vector[flights.GEO_ALTITUDE] = None
        contact = flights.Aircraft(vector, HOME, NOW)
        assert contact.altitude is None
        assert contact.altitude_text() == "--"

    def test_missing_speed_and_track(self):
        vector = list(AIRBORNE)
        vector[flights.VELOCITY] = None
        vector[flights.TRUE_TRACK] = None
        contact = flights.Aircraft(vector, HOME, NOW)
        assert contact.ground_speed is None
        assert contact.track is None
        assert contact.speed_text() == "--"

    def test_short_vector_does_not_explode(self):
        # Defensive: the documented vector is 17 long, but nothing about the
        # wire format stops a shorter one arriving.
        contact = flights.Aircraft(["abc123", "TEST    "], HOME, NOW)
        assert contact.callsign == "TEST"
        assert contact.altitude is None
        assert not contact.located

    def test_label_falls_back_to_the_mode_s_address(self):
        vector = list(AIRBORNE)
        vector[flights.CALLSIGN] = None
        assert flights.Aircraft(vector, HOME, NOW).label() == "4068F5"

    def test_position_source_names(self):
        for index, name in enumerate(("ADS-B", "ASTERIX", "MLAT", "FLARM")):
            vector = list(AIRBORNE)
            vector[flights.POSITION_SOURCE] = index
            assert flights.Aircraft(vector, HOME, NOW).position_source == name


class TestRangeAndBearing:
    """OpenSky gives a box and no ranges, so we work them out."""

    def test_distance_and_bearing_are_computed(self):
        vector = list(AIRBORNE)
        vector[flights.LATITUDE] = 53.4548  # 0.1 deg due north of home
        vector[flights.LONGITUDE] = -1.4839
        contact = flights.Aircraft(vector, HOME, NOW)
        assert contact.distance == pytest.approx(6.0, abs=0.1)
        assert contact.bearing == pytest.approx(0.0, abs=0.1)
        assert contact.plottable

    def test_no_home_leaves_it_unplottable(self):
        contact = flights.Aircraft(AIRBORNE, None, NOW)
        assert contact.located
        assert not contact.plottable

    def test_no_position_at_all(self):
        vector = list(AIRBORNE)
        vector[flights.LATITUDE] = None
        vector[flights.LONGITUDE] = None
        contact = flights.Aircraft(vector, HOME, NOW)
        assert not contact.located
        assert not contact.plottable

    def test_position_age(self):
        vector = list(AIRBORNE)
        vector[flights.TIME_POSITION] = NOW - 45
        assert flights.Aircraft(vector, HOME, NOW).position_age == 45


class TestUrgency:
    @pytest.mark.parametrize("squawk", ["7500", "7600", "7700"])
    def test_emergency_squawks(self, squawk):
        vector = list(AIRBORNE)
        vector[flights.SQUAWK] = squawk
        assert flights.Aircraft(vector, HOME, NOW).urgent

    def test_an_ordinary_squawk_is_not_urgent(self):
        assert not flights.Aircraft(AIRBORNE, HOME, NOW).urgent


class TestParse:
    def _at(self, distance_deg, callsign, ground=False):
        vector = list(ON_GROUND if ground else AIRBORNE)
        vector[flights.CALLSIGN] = callsign
        vector[flights.LATITUDE] = HOME[0] + distance_deg
        vector[flights.LONGITUDE] = HOME[1]
        vector[flights.TIME_POSITION] = NOW
        return vector

    def test_sorts_nearest_first(self):
        payload = envelope(self._at(0.5, "FAR"), self._at(0.05, "NEAR"),
                           self._at(0.2, "MID"))
        assert [c.label() for c in flights.parse(payload, HOME)] == [
            "NEAR", "MID", "FAR"
        ]

    def test_radius_trims_the_box_back_to_a_circle(self):
        # 0.5 deg of latitude is 30 NM, so this one sits just outside.
        payload = envelope(self._at(0.1, "IN"), self._at(0.55, "OUT"))
        assert [c.label() for c in flights.parse(payload, HOME, radius=30)] == ["IN"]

    def test_ground_traffic_is_excluded_by_default(self):
        payload = envelope(self._at(0.05, "TAXIING", ground=True),
                           self._at(0.1, "FLYING"))
        assert [c.label() for c in flights.parse(payload, HOME)] == ["FLYING"]
        both = flights.parse(payload, HOME, include_ground=True)
        assert [c.label() for c in both] == ["TAXIING", "FLYING"]

    def test_stale_positions_are_dropped(self):
        fresh = self._at(0.1, "FRESH")
        stale = self._at(0.05, "STALE")
        stale[flights.TIME_POSITION] = NOW - 600
        payload = envelope(fresh, stale)
        assert [c.label() for c in flights.parse(payload, HOME, max_age=120)] == [
            "FRESH"
        ]
        assert len(flights.parse(payload, HOME)) == 2

    def test_limit_keeps_the_nearest(self):
        payload = envelope(*[
            self._at(0.02 * (index + 1), "AC{}".format(index)) for index in range(20)
        ])
        parsed = flights.parse(payload, HOME, limit=5)
        assert len(parsed) == 5
        assert parsed[0].label() == "AC0"

    def test_empty_sky(self):
        # OpenSky sends states: null rather than an empty list.
        assert flights.parse({"time": NOW, "states": None}, HOME) == []

    def test_tolerates_junk(self):
        assert flights.parse({}, HOME) == []
        assert flights.parse({"states": ["not a vector", 7]}, HOME) == []
        assert flights.parse("not a response", HOME) == []


class TestResponseError:
    def test_healthy_response(self):
        assert flights.response_error(envelope(AIRBORNE)) == ""

    def test_empty_sky_is_not_an_error(self):
        assert flights.response_error({"time": NOW, "states": None}) == ""

    def test_error_payload(self):
        assert flights.response_error({"error": "nope"}) == "nope"
        assert "expired" in flights.response_error({"error_description": "expired"})

    def test_missing_states_key(self):
        assert flights.response_error({"time": NOW}) == "unexpected response"

    def test_not_a_dict(self):
        assert flights.response_error(None) == "bad response"


class TestFormatting:
    @pytest.mark.parametrize(
        "value,expected",
        [(0, "0"), (7, "7"), (999, "999"), (1000, "1,000"), (38000, "38,000"),
         (1234567, "1,234,567"), (-4500, "-4,500")],
    )
    def test_group_digits(self, value, expected):
        assert flights.group_digits(value) == expected

    def test_altitude_text(self):
        vector = list(AIRBORNE)
        vector[flights.BARO_ALTITUDE] = 38000 / 3.280840  # metres
        assert flights.Aircraft(vector, HOME, NOW).altitude_text() == "38,000 ft"

    def test_close_distances_get_a_decimal(self):
        assert placed(4.0, 0.0).distance_text("nm") == "4.0"
        assert placed(2.44, 0.0).distance_text("nm") == "2.4"
        # Past ten the decimal is noise, so it goes.
        assert placed(40.4, 0.0).distance_text("nm") == "40"

    def test_distance_in_other_units(self):
        contact = placed(20.0, 0.0)
        assert contact.distance_text("nm") == "20"
        assert contact.distance_text("km") == "37"   # 20 NM is 37.04 km
        assert contact.distance_text("mi") == "23"   # and 23.0 statute miles

    @pytest.mark.parametrize(
        "bearing,expected",
        [(0.0, "N 000"), (31.0, "NNE 031"), (90.0, "E 090"), (225.0, "SW 225")],
    )
    def test_bearing_text_is_padded(self, bearing, expected):
        assert placed(10.0, bearing).bearing_text() == expected

    def test_trend(self):
        for rate, expected in ((5.0, "climbing"), (-5.0, "descending"),
                               (0.0, "level")):
            vector = list(AIRBORNE)
            vector[flights.VERTICAL_RATE] = rate
            assert flights.Aircraft(vector, HOME, NOW).trend_text() == expected

    def test_origin_text(self):
        assert flights.Aircraft(AIRBORNE, HOME, NOW).origin_text() == "United Kingdom"


class TestDemoSky:
    def test_looks_like_a_real_response(self):
        payload = DemoSky(HOME[0], HOME[1], 30.0).step(1000)
        assert flights.response_error(payload) == ""
        assert len(payload["states"][0]) == flights.VECTOR_LENGTH

    def test_survives_the_metric_round_trip(self):
        # The demo thinks in feet and knots and emits metres and m/s, which
        # is the same conversion the real feed's numbers go through.
        payload = DemoSky(HOME[0], HOME[1], 30.0).step(0)
        contacts = flights.parse(payload, HOME)
        speeds = sorted(round(c.ground_speed) for c in contacts)
        assert speeds == [180, 225, 270, 315, 360, 405]

    def test_traffic_stays_inside_the_scope(self):
        sky = DemoSky(HOME[0], HOME[1], 30.0)
        for _tick in range(40):
            for contact in flights.parse(sky.step(2500), HOME, radius=30):
                assert 0.0 <= contact.distance <= 30.0

    def test_the_fleet_is_not_in_lockstep(self):
        # An integer phase offset would have every aircraft climbing and
        # descending together, which looks obviously fake.
        contacts = flights.parse(DemoSky(HOME[0], HOME[1], 30.0).step(5000), HOME)
        assert len({contact.trend_text() for contact in contacts}) > 1

    def test_the_closest_aircraft_changes_over_time(self):
        sky = DemoSky(HOME[0], HOME[1], 30.0)
        seen = set()
        for _tick in range(60):
            seen.add(flights.parse(sky.step(2000), HOME)[0].label())
        assert len(seen) > 1
