"""Tests for the great-circle maths behind the scope.

    pytest tests

conftest.py puts the device modules on sys.path.
"""

import math

import pytest

import geo


class TestDistance:
    def test_known_leg(self):
        # Heathrow to Charles de Gaulle, a little over 187 NM.
        distance = geo.distance_nm(51.4700, -0.4543, 49.0097, 2.5479)
        assert distance == pytest.approx(187.3, abs=1.0)

    def test_a_degree_of_latitude_is_sixty_miles(self):
        # The nautical mile is defined as a minute of arc, so this is a check
        # on EARTH_RADIUS_NM rather than on the formula.
        assert geo.distance_nm(0.0, 0.0, 1.0, 0.0) == pytest.approx(60.0, abs=0.2)

    def test_same_point_is_zero(self):
        # The haversine's asin(sqrt(a)) is the step that trips over a value a
        # hair above 1.0 for coincident points.
        assert geo.distance_nm(53.3548, -1.4839, 53.3548, -1.4839) == 0.0

    def test_symmetric(self):
        there = geo.distance_nm(53.3548, -1.4839, 51.5074, -0.1278)
        back = geo.distance_nm(51.5074, -0.1278, 53.3548, -1.4839)
        assert there == pytest.approx(back)

    def test_across_the_antimeridian(self):
        # Two points a degree apart either side of 180, not 359 degrees apart.
        assert geo.distance_nm(0.0, 179.5, 0.0, -179.5) == pytest.approx(60.0, abs=0.2)


class TestBearing:
    @pytest.mark.parametrize(
        "lat,lon,expected",
        [(1.0, 0.0, 0.0), (0.0, 1.0, 90.0), (-1.0, 0.0, 180.0), (0.0, -1.0, 270.0)],
    )
    def test_cardinals_from_the_origin(self, lat, lon, expected):
        assert geo.bearing_deg(0.0, 0.0, lat, lon) == pytest.approx(expected, abs=0.1)

    def test_always_positive(self):
        bearing = geo.bearing_deg(53.3548, -1.4839, 51.5074, -0.1278)
        assert 0.0 <= bearing < 360.0


class TestProject:
    @pytest.mark.parametrize("bearing", [0.0, 45.0, 137.0, 210.0, 359.0])
    @pytest.mark.parametrize("distance", [0.5, 12.0, 120.0])
    def test_round_trips(self, bearing, distance):
        """project is the inverse of distance_nm/bearing_deg."""
        latitude, longitude = geo.project(53.3548, -1.4839, bearing, distance)
        assert geo.distance_nm(53.3548, -1.4839, latitude, longitude) == pytest.approx(
            distance, rel=1e-6
        )
        assert geo.bearing_deg(53.3548, -1.4839, latitude, longitude) == pytest.approx(
            bearing, abs=0.01
        )

    def test_longitude_stays_in_range(self):
        _latitude, longitude = geo.project(0.0, 179.9, 90.0, 60.0)
        assert -180.0 <= longitude <= 180.0


class TestCompassPoint:
    @pytest.mark.parametrize(
        "bearing,expected",
        [(0, "N"), (22.5, "NNE"), (45, "NE"), (90, "E"), (180, "S"), (270, "W"),
         (348.75, "N"), (360, "N"), (-90, "W")],
    )
    def test_points(self, bearing, expected):
        assert geo.compass_point(bearing) == expected


class TestRadarOffset:
    def test_north_is_up(self):
        dx, dy = geo.radar_offset(0.0, 10.0, 10.0, 100)
        assert dx == pytest.approx(0.0, abs=1e-9)
        assert dy == pytest.approx(-100.0)

    def test_east_is_right(self):
        dx, dy = geo.radar_offset(90.0, 10.0, 10.0, 100)
        assert dx == pytest.approx(100.0)
        assert dy == pytest.approx(0.0, abs=1e-9)

    def test_centre_when_on_top_of_us(self):
        assert geo.radar_offset(45.0, 0.0, 10.0, 100) == (0.0, 0.0)

    def test_beyond_range_pins_to_the_edge(self):
        dx, dy = geo.radar_offset(90.0, 400.0, 10.0, 100)
        assert math.hypot(dx, dy) == pytest.approx(100.0)

    def test_zero_span_does_not_divide_by_zero(self):
        assert geo.radar_offset(90.0, 5.0, 0.0, 100) == (0.0, 0.0)


class TestBoundingBox:
    def test_encloses_the_circle(self):
        lamin, lomin, lamax, lomax = geo.bounding_box(53.3548, -1.4839, 30)
        for bearing in range(0, 360, 5):
            latitude, longitude = geo.project(53.3548, -1.4839, bearing, 30)
            assert lamin <= latitude <= lamax
            assert lomin <= longitude <= lomax

    def test_a_degree_of_latitude_is_sixty_miles(self):
        lamin, _lomin, lamax, _lomax = geo.bounding_box(0.0, 0.0, 60)
        assert lamax - lamin == pytest.approx(2.0)

    def test_longitude_widens_towards_the_poles(self):
        at_equator = geo.bounding_box(0.0, 0.0, 30)
        up_north = geo.bounding_box(60.0, 0.0, 30)
        assert geo.box_area(up_north) > geo.box_area(at_equator) * 1.9

    def test_stays_inside_valid_coordinates(self):
        for latitude in (89.9, -89.9, 0.0):
            for longitude in (179.9, -179.9, 0.0):
                lamin, lomin, lamax, lomax = geo.bounding_box(latitude, longitude, 200)
                assert -90.0 <= lamin <= lamax <= 90.0
                assert -180.0 <= lomin <= lomax <= 180.0

    def test_a_pole_does_not_divide_by_zero(self):
        box = geo.bounding_box(90.0, 0.0, 30)
        assert geo.box_area(box) > 0

    def test_box_area(self):
        assert geo.box_area((0.0, 0.0, 2.0, 3.0)) == pytest.approx(6.0)


class TestUnits:
    def test_conversions(self):
        assert geo.convert(10.0, "nm") == 10.0
        assert geo.convert(10.0, "km") == pytest.approx(18.52)
        assert geo.convert(10.0, "mi") == pytest.approx(11.50779)

    def test_unknown_unit_stays_nautical(self):
        assert geo.convert(10.0, "furlongs") == 10.0
        assert geo.unit_label("furlongs") == "NM"

    def test_labels(self):
        assert geo.unit_label("km") == "KM"
        assert geo.unit_label("mi") == "MI"
