#!/usr/bin/env python3
"""Check what OpenSky will give you, and how fast you may ask for it.

OpenSky needs no account, but it meters queries in credits - 400 a day
anonymously, counted per IP address, and 4000 with a free one. This works
out what a query from here costs, what you have left, and therefore how
often the Presto can poll without running dry before the day is out.

    python pc/check_access.py                       # anonymous, locate by IP
    python pc/check_access.py --lat 53.35 --lon -1.48 --radius 30
    python pc/check_access.py --client-id ID --client-secret SECRET
    python pc/check_access.py --save sky.json       # keep the response

A saved response can be drawn with pc/preview.py --payload, which is a way
to lay the screen out against your own sky without a board attached.

Note that a run of this spends a credit from the same daily allowance the
Presto draws on, since both are billed to this network's address.

Standard library only - no pip install needed.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "device"))

import flights  # noqa: E402 - needs the path above
import geo  # noqa: E402
import netapi  # noqa: E402

DEFAULT_BASE = "https://opensky-network.org/api"
TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/opensky-network"
    "/protocol/openid-connect/token"
)
LOCATION_URL = "http://ip-api.com/json/?fields=status,message,country,city,lat,lon"
USER_AGENT = "presto-deck-flight-tracker/1.0"
SECONDS_PER_DAY = 86400


def get_json(url, headers=None, data=None, timeout=20):
    """(payload, status, headers). Raises only when there was nothing to read."""
    request = urllib.request.Request(
        url, headers=dict(headers or {}, **{"User-Agent": USER_AGENT}),
        data=data.encode() if data else None,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read()), response.status, dict(response.headers)
    except urllib.error.HTTPError as error:
        body = error.read()
        try:
            return json.loads(body), error.code, dict(error.headers)
        except ValueError:
            return {"error": body.decode("utf-8", "replace").strip()}, error.code, {}


def locate():
    payload, status, _headers = get_json(LOCATION_URL)
    if status != 200 or payload.get("status") != "success":
        raise SystemExit("Could not locate you by IP: {}".format(payload))
    where = payload.get("city") or payload.get("country") or "somewhere"
    print("Your IP puts you near {} at {:.4f}, {:.4f}".format(
        where, payload["lat"], payload["lon"]))
    return payload["lat"], payload["lon"]


def authenticate(client_id, client_secret):
    """A bearer-token header, or {} to stay anonymous."""
    if not (client_id and client_secret):
        print("No credentials given - going out anonymously (400 credits/day).")
        return {}, netapi.ANONYMOUS_DAILY_CREDITS

    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    })
    payload, status, _headers = get_json(
        TOKEN_URL, {"Content-Type": "application/x-www-form-urlencoded"}, body
    )
    if status != 200 or not payload.get("access_token"):
        raise SystemExit("Authentication failed (HTTP {}): {}".format(
            status, payload.get("error_description") or payload))
    print("Authenticated - token good for {}s.".format(payload.get("expires_in", "?")))
    return ({"Authorization": "Bearer " + payload["access_token"]},
            netapi.REGISTERED_DAILY_CREDITS)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--lat", type=float, help="skip the IP lookup")
    parser.add_argument("--lon", type=float)
    parser.add_argument("--radius", type=float, default=30.0, help="nautical miles")
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--client-id", default=os.environ.get("OPENSKY_CLIENT_ID", ""))
    parser.add_argument("--client-secret",
                        default=os.environ.get("OPENSKY_CLIENT_SECRET", ""))
    parser.add_argument("--ground", action="store_true",
                        help="count aircraft on the ground too")
    parser.add_argument("--save", help="write the response to this file")
    args = parser.parse_args()

    if args.lat is None or args.lon is None:
        latitude, longitude = locate()
    else:
        latitude, longitude = args.lat, args.lon

    headers, daily = authenticate(args.client_id, args.client_secret)

    box = geo.bounding_box(latitude, longitude, args.radius)
    area = geo.box_area(box)
    cost = netapi.credit_cost(area)
    print("\nA {:g} NM circle is a {:.2f} sq deg box, which costs {} credit(s) "
          "per request.".format(args.radius, area, cost))
    print("An allowance of {} credits/day is {} of those, one every {:.0f}s.".format(
        daily, daily // cost, SECONDS_PER_DAY / (daily / cost)))

    url = netapi.states_url(args.base, latitude, longitude, args.radius)
    print("\nGET " + url)
    payload, status, response_headers = get_json(url, headers)

    if status != 200:
        print("\nHTTP {} - {}".format(status, netapi.status_message(status)))
        print("The feed said: {}".format(payload))
        return 1

    error = flights.response_error(payload)
    if error:
        print("\nThe feed returned an error: {}".format(error))
        return 1

    remaining = netapi.credits_remaining(response_headers)
    states = payload.get("states") or []
    aircraft = flights.parse(payload, (latitude, longitude), radius=args.radius,
                             include_ground=args.ground)
    print("\nOK - {} state vectors in the box, {} within {:g} NM{}.".format(
        len(states), len(aircraft), args.radius,
        "" if args.ground else " and airborne"))

    if remaining is not None:
        print("{} credits left today. Spread over a further 24 hours that is "
              "one request every {:.0f}s.".format(
                  remaining, SECONDS_PER_DAY / max(remaining / cost, 1e-9)))

    for contact in aircraft[:5]:
        print("  {:<9} {:<20} {:>10}  {:>7}  {:>5} NM  {}".format(
            contact.label(),
            contact.origin_text()[:20],
            contact.altitude_text(),
            contact.speed_text(),
            contact.distance_text("nm"),
            contact.bearing_text()))

    if args.save:
        with open(args.save, "w") as handle:
            json.dump(payload, handle)
        print("\nSaved to {} - draw it with:\n  python pc/preview.py "
              "--payload {} --lat {} --lon {}".format(
                  args.save, args.save, latitude, longitude))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
