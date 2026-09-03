"""Tweakables for the Presto flight tracker.

Copy this file (and the rest of device/) to the root of your Presto.
"""

# Personal settings - your coordinates and your OpenSky credentials - live in
# secrets.py alongside the WiFi details, because that file is gitignored and
# this one is not. Anything missing there falls back to the defaults below, so
# the tracker still runs with no secrets.py at all.
try:
    import secrets as _secrets
except ImportError:  # no secrets.py on the device yet
    _secrets = None


def _secret(name, default):
    return getattr(_secrets, name, default) if _secrets else default


# --- Display -----------------------------------------------------------------
# A crisp 480x480. The screen is text-heavy and only changes every
# REFRESH_SECONDS, so it can afford the frame rate: about 6fps against 10 at
# 240x240, which only governs how quickly a tap registers. The layout is drawn
# from display.get_bounds() and scales either way, so False is a fair choice
# if you want the extra responsiveness.
FULL_RES = True

# Upper bound, not a busy loop - there is nothing to animate between refreshes
# beyond the countdown ring, so this only really governs touch response.
TARGET_FPS = 10

# Screen brightness, 0.0 - 1.0.
BACKLIGHT = 1.0

# Use PicoVector text if a .af font is present on the device (nicer, slower).
# Falls back to the built-in bitmap font automatically.
VECTOR_FONT = "Roboto-Medium.af"

# --- Where you are -----------------------------------------------------------
# LATITUDE/LONGITUDE of None look the position up from your public IP at boot -
# one request, at startup only. Setting both skips that lookup, which is worth
# doing: an IP lookup is accurate to the town at best, and to your ISP's
# nearest exchange at worst.
LATITUDE = _secret("LATITUDE", None)
LONGITUDE = _secret("LONGITUDE", None)

# Shown in the status bar. Blank uses the city name from the IP lookup.
LOCATION_NAME = _secret("LOCATION_NAME", "")

# Free, no key, 45 requests a minute. HTTP only on the free tier - see
# netapi.locate().
LOCATION_URL = "http://ip-api.com/json/?fields=status,message,country,city,lat,lon"

# --- The feed ----------------------------------------------------------------
# https://openskynetwork.github.io/opensky-api/ - a community ADS-B network,
# free and usable with no account at all.
OPENSKY_BASE = "https://opensky-network.org/api"

# OpenSky prices each query in "credits" and allows a fixed number per day:
# 400 anonymously (counted per IP address), 4000 with a free account. Leave
# these blank to stay anonymous; fill them in from an API client created at
# https://opensky-network.org/my-opensky to get the larger allowance and the
# 30 second refresh below.
OPENSKY_CLIENT_ID = _secret("OPENSKY_CLIENT_ID", "")
OPENSKY_CLIENT_SECRET = _secret("OPENSKY_CLIENT_SECRET", "")
OPENSKY_TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/opensky-network"
    "/protocol/openid-connect/token"
)

# Radius of the scope, nautical miles. OpenSky queries a bounding box, so a
# larger circle costs more credits per request: up to about 120 NM is one
# credit, and 250 NM is three. Contacts outside the circle are discarded.
RADIUS_NM = 30

# Seconds between requests, and the floor a slip of the keyboard cannot get
# below. 30 seconds is 2880 requests a day, which fits a registered account's
# allowance and is seven times an anonymous one - so leave ADAPTIVE_REFRESH on
# and let the tracker stretch the interval to whatever today's credits afford
# (about 3.5 minutes anonymously). Turning it off will exhaust the allowance
# and leave you looking at "429 - out of credits" for the rest of the day.
REFRESH_SECONDS = 30
MIN_REFRESH_SECONDS = 10
ADAPTIVE_REFRESH = True

# Give up on a request after this long, and back off on repeated failures -
# doubling from the refresh interval up to this ceiling - so an outage is
# retried gently rather than every 30 seconds forever.
REQUEST_TIMEOUT = 10
MAX_BACKOFF_SECONDS = 600

# Drop contacts whose position is older than this. OpenSky keeps an aircraft
# in the feed for a while after its last message, and a blip frozen where
# something was last heard ten minutes ago is worse than no blip.
MAX_POSITION_AGE_SECONDS = 120

# Include aircraft on the ground. An airport inside the circle otherwise
# contributes a dozen taxiing contacts in one grey clump, and none of them is
# flying over you.
SHOW_GROUND_TRAFFIC = False

# Most aircraft kept and drawn. Somewhere busy can return well over a hundred
# inside 30 NM, which is more contacts than a 480 pixel scope can separate.
MAX_AIRCRAFT = 40

# --- Readout -----------------------------------------------------------------
# Distance on the scope and in the panel: "nm", "km" or "mi". Altitude is
# always feet and speed always knots, which is what aviation uses and what
# the feed reports.
DISTANCE_UNITS = "nm"

# Tint the 7 ambient LEDs with the closest aircraft's altitude colour,
# brightening as it gets nearer, so the unit glows when something passes
# overhead. Off by default - it is a lot of light for a shelf in a dark room.
AMBIENT_LEDS = False

# Fly synthetic traffic when the feed cannot be reached - no API access yet,
# no WiFi, or an outage. The real feed is still retried in the background and
# takes over the moment it answers.
DEMO_WHEN_UNAVAILABLE = True
