"""Great-circle maths for the flight tracker.

Distances are nautical miles and bearings degrees true, the units aviation
works in. OpenSky answers with a bounding box and no ranges at all, so
everything the scope needs to place a contact is worked out here.

Plain Python with nothing but `math`, so it runs under CPython too - see
tests/test_geo.py.
"""

import math

# Mean earth radius. In nautical miles by definition of the unit: one minute
# of arc, so a degree of latitude is 60 of these.
EARTH_RADIUS_NM = 3440.065

NM_TO_KM = 1.852
NM_TO_MI = 1.150779

COMPASS = (
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
)


def distance_nm(lat1, lon1, lat2, lon2):
    """Great-circle distance between two points, in nautical miles."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lambda = math.radians(lon2 - lon1)

    # Haversine: better conditioned than the spherical law of cosines at the
    # short ranges a radar screen cares about.
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    # Rounding can push `a` a hair outside [0, 1] for coincident points.
    a = min(1.0, max(0.0, a))
    return 2 * EARTH_RADIUS_NM * math.asin(math.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2):
    """Initial bearing from point 1 to point 2, degrees true (0-360)."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)

    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(
        delta_lambda
    )
    return math.degrees(math.atan2(y, x)) % 360.0


def project(lat, lon, bearing, distance):
    """The point `distance` nautical miles from (lat, lon) along `bearing`.

    The inverse of distance_nm/bearing_deg, used to place the demo traffic.
    """
    angular = distance / EARTH_RADIUS_NM
    phi1 = math.radians(lat)
    lambda1 = math.radians(lon)
    theta = math.radians(bearing)

    sin_phi2 = math.sin(phi1) * math.cos(angular) + math.cos(phi1) * math.sin(
        angular
    ) * math.cos(theta)
    sin_phi2 = min(1.0, max(-1.0, sin_phi2))
    phi2 = math.asin(sin_phi2)
    lambda2 = lambda1 + math.atan2(
        math.sin(theta) * math.sin(angular) * math.cos(phi1),
        math.cos(angular) - math.sin(phi1) * sin_phi2,
    )
    # Back into -180..180 so the result survives a round trip across the
    # antimeridian.
    return math.degrees(phi2), (math.degrees(lambda2) + 540.0) % 360.0 - 180.0


def compass_point(bearing):
    """Bearing as one of the 16 compass points - "N", "ENE", "SW" ..."""
    return COMPASS[int((bearing % 360.0) / 22.5 + 0.5) % 16]


def radar_offset(bearing, distance, span, radius):
    """(dx, dy) pixels from the radar centre for a contact.

    Screen y grows downward, so north is -y. Contacts past `span` are pinned
    to the edge rather than drawn outside the scope.
    """
    if span <= 0:
        return 0.0, 0.0
    scale = radius * min(distance / span, 1.0)
    theta = math.radians(bearing)
    return scale * math.sin(theta), -scale * math.cos(theta)


def bounding_box(latitude, longitude, radius):
    """(lamin, lomin, lamax, lomax) enclosing a circle of `radius` NM.

    OpenSky filters by box rather than by circle, so a query built from this
    also returns the corners - up to 27% more sky than asked for. The caller
    throws those away by distance; see flights.parse.

    The box is clamped to the valid coordinate ranges, so a circle over a
    pole or across the antimeridian comes back truncated rather than wrong.
    """
    # A degree of latitude is 60 NM, by the definition of the nautical mile.
    latitude_span = radius / 60.0
    lamin = max(-90.0, latitude - latitude_span)
    lamax = min(90.0, latitude + latitude_span)

    # Meridians converge, so a degree of longitude is only 60 NM at the
    # equator. Scale by the cosine of whichever edge of the box lies furthest
    # from it, which is where longitude degrees are shortest.
    worst = min(89.9, max(abs(lamin), abs(lamax)))
    scale = math.cos(math.radians(worst))
    longitude_span = 180.0 if scale < 1e-6 else min(180.0, latitude_span / scale)

    return (
        lamin,
        max(-180.0, longitude - longitude_span),
        lamax,
        min(180.0, longitude + longitude_span),
    )


def box_area(box):
    """Area of a bounding box in square degrees.

    Not a real area - it does not account for convergence - but it is the
    number OpenSky prices a query on, so it is the one worth reporting.
    """
    lamin, lomin, lamax, lomax = box
    return (lamax - lamin) * (lomax - lomin)


def convert(distance, units):
    """Nautical miles into the configured display unit."""
    if units == "km":
        return distance * NM_TO_KM
    if units == "mi":
        return distance * NM_TO_MI
    return distance


def unit_label(units):
    return {"km": "KM", "mi": "MI"}.get(units, "NM")
