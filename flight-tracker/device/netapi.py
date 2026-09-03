"""The HTTP calls the flight tracker makes: where we are, what is overhead.

Both block. At one request every refresh interval that is far cheaper than
holding a socket open, and a failed call costs nothing but a frame - the last
snapshot stays on screen while the caller backs off and tries again.

OpenSky prices queries in credits: a small bounding box is one credit, and an
anonymous caller gets 400 a day. Every response says how many are left in the
`x-rate-limit-remaining` header, which is what lets main.py pace itself
rather than guess - see credits_remaining() and credit_cost().

`requests` comes from the networking bundle frozen into the Presto firmware.
It is imported lazily so this module still imports on a host with no such
library, which is what lets the tests exercise the URL and credit maths.
"""

import geo

# Anything past this and we are being sent more sky than the screen can use.
MAX_RADIUS_NM = 250

# A busy box is tens of kilobytes of JSON, which the Presto's PSRAM takes in
# its stride, but a mistyped radius should not be able to exhaust it.
MAX_RESPONSE_BYTES = 512 * 1024

# How OpenSky prices /states/all, by bounding box area in square degrees.
CREDIT_BANDS = ((25.0, 1), (100.0, 2), (400.0, 3))
MAX_CREDIT_COST = 4

RATE_LIMIT_HEADER = "x-rate-limit-remaining"

# What OpenSky says a token lasts, used when a response does not say.
DEFAULT_TOKEN_LIFETIME_MS = 30 * 60 * 1000

# Daily allowances, for working out how fast we may poll. Anonymous callers
# are bucketed by IP address.
ANONYMOUS_DAILY_CREDITS = 400
REGISTERED_DAILY_CREDITS = 4000


class ApiError(Exception):
    """A request that did not come back with usable JSON.

    `status` is the HTTP status when there was one, otherwise None.
    """

    def __init__(self, message, status=None):
        Exception.__init__(self, message)
        self.message = message
        self.status = status

    def __str__(self):
        return self.message


def credit_cost(area):
    """What OpenSky charges for a box of `area` square degrees."""
    for limit, cost in CREDIT_BANDS:
        if area <= limit:
            return cost
    return MAX_CREDIT_COST


def states_url(base, latitude, longitude, radius):
    """The /states/all URL for a circle of `radius` nautical miles.

    OpenSky takes a bounding box, so the circle is squared off here and
    trimmed back to a circle in flights.parse. Coordinates are given to 4
    decimal places - about 10 metres, far finer than an IP lookup knows.
    """
    radius = max(1.0, min(float(radius), MAX_RADIUS_NM))
    lamin, lomin, lamax, lomax = geo.bounding_box(latitude, longitude, radius)
    return (
        "{}/states/all?lamin={:.4f}&lomin={:.4f}&lamax={:.4f}&lomax={:.4f}".format(
            base.rstrip("/"), lamin, lomin, lamax, lomax
        )
    )


def credits_remaining(headers):
    """The credits left in today's allowance, or None if unstated.

    Header names keep whatever case the server sent, so match them loosely.
    """
    if not headers:
        return None
    for name in headers:
        if str(name).lower() == RATE_LIMIT_HEADER:
            try:
                return int(str(headers[name]).strip())
            except (TypeError, ValueError):
                return None
    return None


def status_message(status):
    if status == 401:
        return "401 - check credentials"
    if status == 403:
        return "403 - not permitted"
    if status == 429:
        # The daily credit allowance is spent; it resets on its own.
        return "429 - out of credits"
    if status >= 500:
        return "{} - feed unavailable".format(status)
    return "HTTP {}".format(status)


def _request(url, headers=None, timeout=10, data=None):
    """GET (or POST, with `data`) and decode JSON. Returns (payload, headers)."""
    import requests

    response = None
    try:
        try:
            if data is None:
                response = requests.get(url, headers=headers or {}, timeout=timeout)
            else:
                response = requests.post(
                    url, headers=headers or {}, data=data, timeout=timeout
                )
        except Exception as error:  # noqa: BLE001 - DNS, TLS, routing, timeout
            raise ApiError("network: {}".format(error)) from error

        status = response.status_code
        if status != 200:
            raise ApiError(status_message(status), status)

        body = response.content
        if len(body) > MAX_RESPONSE_BYTES:
            raise ApiError("response too large", status)
        try:
            import json

            return json.loads(body), getattr(response, "headers", None)
        except (ValueError, TypeError) as error:
            raise ApiError("bad json: {}".format(error), status) from error
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:  # noqa: BLE001 - already unwinding
                pass


class TokenSource:
    """OAuth2 client-credentials tokens, refreshed before they expire.

    OpenSky tokens last 30 minutes. With no client id and secret configured
    this does nothing at all and requests go out anonymously, which works -
    it just buys a much smaller daily allowance.
    """

    def __init__(self, token_url, client_id, client_secret, timeout=10, margin_ms=60000):
        self.token_url = token_url
        self.client_id = client_id or ""
        self.client_secret = client_secret or ""
        self.timeout = timeout
        self.margin_ms = margin_ms
        # No token legitimately outlives this; see _valid_at.
        self.lifetime_cap_ms = 24 * 60 * 60 * 1000
        self._token = None
        self._expires_at = 0

    @property
    def enabled(self):
        return bool(self.client_id and self.client_secret)

    @property
    def daily_credits(self):
        return REGISTERED_DAILY_CREDITS if self.enabled else ANONYMOUS_DAILY_CREDITS

    def headers(self, now_ms):
        """The Authorization header to send, or {} when anonymous.

        `now_ms` is a millisecond tick count from the caller - main.py's
        time.ticks_ms() - so this class needs no clock of its own.
        """
        if not self.enabled:
            return {}
        token = self._token
        if token is None or not self._valid_at(now_ms):
            token = self._refresh(now_ms)
        return {"Authorization": "Bearer " + token}

    def _valid_at(self, now_ms):
        """True while the cached token is still worth sending.

        ticks_ms() wraps, so a deadline that looks absurdly far ahead is one
        the counter has already rolled past rather than one genuinely in the
        future. Bounding the remaining time from both ends catches that
        without needing ticks_diff, at the cost of one early renewal
        whenever the counter happens to wrap.
        """
        remaining = self._expires_at - now_ms
        return 0 < remaining <= self.lifetime_cap_ms

    def forget(self):
        """Drop the cached token, so the next call fetches a fresh one."""
        self._token = None

    def _refresh(self, now_ms):
        body = "grant_type=client_credentials&client_id={}&client_secret={}".format(
            self.client_id, self.client_secret
        )
        payload, _headers = _request(
            self.token_url,
            {"Content-Type": "application/x-www-form-urlencoded"},
            self.timeout,
            body,
        )
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not token or not isinstance(token, str):
            raise ApiError("no access token in the auth response")

        lifetime = payload.get("expires_in")
        lifetime_ms = DEFAULT_TOKEN_LIFETIME_MS
        if isinstance(lifetime, (int, float)) and lifetime > 0:
            lifetime_ms = int(lifetime) * 1000

        self._token = token
        # Renew early, so a token cannot expire midway through a request.
        self._expires_at = now_ms + max(1, lifetime_ms - self.margin_ms)
        return token


def fetch_states(base, latitude, longitude, radius, headers=None, timeout=10):
    """(payload, credits remaining) for the aircraft around a point."""
    payload, response_headers = _request(
        states_url(base, latitude, longitude, radius), headers, timeout
    )
    return payload, credits_remaining(response_headers)


def locate(url, timeout=10):
    """(latitude, longitude, place name) for our public IP address.

    ip-api.com needs no key and allows 45 requests a minute, which is ample
    for the one call we make at boot. Its free tier is plain HTTP only; the
    request carries nothing the far end would not already learn from the
    connection itself.
    """
    payload, _headers = _request(url, timeout=timeout)
    if not isinstance(payload, dict):
        raise ApiError("bad location response")
    if payload.get("status") != "success":
        raise ApiError("location: {}".format(payload.get("message") or "failed"))

    latitude = payload.get("lat")
    longitude = payload.get("lon")
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        raise ApiError("location: no coordinates")

    name = str(payload.get("city") or payload.get("country") or "").strip()
    return float(latitude), float(longitude), name
