# Flight Tracker

A live radar scope for the [Pimoroni Presto](https://github.com/pimoroni/presto):
the aircraft currently flying over your patch of sky, plotted north-up around
your own position, with the closest one written out along the bottom.

```
┌──────────────────────────────────────┐
│ ● Sheffield                   20 AC  │  where we are, contacts in range
│                N                     │
│        ·  ·  ·  ·  ·  ·              │
│     ·    ╭───────────╮    ·  30 NM   │  countdown ring, filling as the
│   ·     ╱      ◤      ╲     ·        │  next refresh comes due
│  ·     │    ◤     ·    │     ·       │  contacts coloured by altitude,
│ W·     │        ⊕      │     ·E      │  pointed along their track
│  ·     │    ◣  ┌◤┐     │     ·       │  ⊕ you    ┌ ┐ selected
│   ·     ╲     AAL79   ╱     ·        │
│     ·    ╰───────────╯    ·          │
│        ·  ·  ·  ·  ·  ·              │
│                S                     │
├──────────────────────────────────────┤
│ AAL79                       10 NM    │  the closest aircraft, or
│ United States               SE 145   │  whichever one you last tapped
│ 33,950 ft  climbing         432 kt   │
└──────────────────────────────────────┘
```

Positions come from the [OpenSky Network](https://openskynetwork.github.io/opensky-api/),
a community ADS-B feed run by a non-profit research consortium. It needs no
account to get started. Set `AMBIENT_LEDS = True` and the 7 ambient LEDs glow
with the closest aircraft's altitude colour, brightening as it gets nearer, so
the unit lights up when something passes overhead - off by default, because it
is a lot of light for a shelf in a dark room.

## Credits, and how often it can poll

OpenSky is free but metered. Every query costs **credits** from a daily
allowance, and how many you get depends on whether you have an account:

| Who you are                                    | Credits/day | One request every |
| ---------------------------------------------- | ----------- | ----------------- |
| Anonymous (counted per IP address)             | 400         | ~3.5 minutes      |
| [Free account](https://opensky-network.org/)   | 4,000       | ~22 seconds       |

A query costs 1 credit for a bounding box up to 25 square degrees, rising to 4
above 400 - so a 30 NM scope is 1 credit and even 120 NM still is. Run
`pc/check_access.py` to see the arithmetic for your own position.

**It works anonymously out of the box**, refreshing roughly every 3.5 minutes.
For the 30 second refresh, create an API client at
[opensky-network.org/my-opensky](https://opensky-network.org/my-opensky) and
put the id and secret in `OPENSKY_CLIENT_ID` / `OPENSKY_CLIENT_SECRET` in
[device/config.py](device/config.py). The tracker handles the OAuth2 token
exchange and renews the token before it expires.

`ADAPTIVE_REFRESH` is what keeps this honest. Every response carries an
`x-rate-limit-remaining` header, and the tracker paces itself to make whatever
is left last a further 24 hours, never polling faster than `REFRESH_SECONDS`.
That is deliberately pessimistic - the allowance resets well before a day is
out - but it needs no clock on a board that has never synchronised one, and it
cannot spend the budget early and leave you staring at `429 - out of credits`
all evening. The cost is that a nearly-spent allowance stretches the interval a
long way: at 50 credits left it will wait half an hour between requests.

Turn it off and the configured interval is used as-is. Anonymously, that will
exhaust the day's credits in about three hours.

## Quick start

Paths and commands below are relative to this directory (`flight-tracker/`).

1. Flash the [Presto MicroPython firmware](https://github.com/pimoroni/presto/releases)
   if you haven't already.
2. Copy everything in [device/](device/) to the root of the Presto (Thonny, or
   `mpremote cp device/*.py :`), plus a `secrets.py` with your WiFi details -
   see [device/secrets.py.example](device/secrets.py.example).
3. Reset the board. It connects to WiFi, works out where it is from your public
   IP, and starts scanning.

Tap the screen to step out through the other aircraft on the scope; the next
refresh puts you back on the closest one.

Check what the feed will give you before you blame the board:

```
python pc/check_access.py
python pc/check_access.py --client-id ID --client-secret SECRET
```

## Where it thinks you are

By default the tracker asks [ip-api.com](http://ip-api.com) what your public IP
maps to - one plain-HTTP request at boot, carrying nothing the far end would
not already learn from the connection itself. That is accurate to the town at
best and to your ISP's nearest exchange at worst, which is fine for a 30 NM
circle and useless for anything smaller.

Set `LATITUDE` and `LONGITUDE` in [device/config.py](device/config.py) to skip
the lookup and put the centre of the scope exactly where you are.

## Reading the screen

Contacts are coloured by altitude, the same banding every ADS-B map uses:

| Altitude            | Colour |
| ------------------- | ------ |
| below 4,000 ft      | red    |
| 4,000 - 8,000 ft    | orange |
| 8,000 - 14,000 ft   | yellow |
| 14,000 - 22,000 ft  | green  |
| 22,000 - 30,000 ft  | cyan   |
| above 30,000 ft     | violet |

Each contact is a triangle pointing along its ground track. Anything squawking
7500, 7600 or 7700 gets red brackets and a red callsign in the panel.

The panel's second line is the country the aircraft is registered in. OpenSky's
state vectors carry no registration or type - its aircraft metadata endpoint
now answers `410 Gone` - so the callsign and the country are the whole of the
identity available.

Things that are deliberately not drawn:

- **Aircraft on the ground.** An airport inside the circle otherwise
  contributes a dozen taxiing contacts in one unreadable grey clump, and none
  of them is flying over anybody. `SHOW_GROUND_TRAFFIC = True` puts them back.
- **Stale positions.** OpenSky keeps an aircraft in the feed for a while after
  its last message; anything older than `MAX_POSITION_AGE_SECONDS` is dropped
  rather than left frozen where it was last heard.
- **Aircraft with no position at all**, which would have to be drawn at a
  guess. Ones with no altitude show a dash, not a zero.

## Working on it without a board

`pc/preview.py` runs the real [device/radar.py](device/radar.py) against a
stand-in for PicoGraphics that writes SVG, so you can see the layout - and
prove it still draws - on a machine with no Presto attached:

```
python pc/preview.py --state normal --state emergency --state no-aircraft
python pc/preview.py --size 240 --units km          # the other resolution
```

To lay the screen out against your own sky, save a real response and draw it:

```
python pc/check_access.py --save sky.json
python pc/preview.py --payload sky.json --lat 53.35 --lon -1.48 --max-age 120
```

The device picks up PicoVector when a `.af` font is on the board; the preview
has no PicoVector, so it shows the built-in bitmap font path. The real thing is
smoother.

## Layout

| Path                                     | What it is                                          |
| ---------------------------------------- | --------------------------------------------------- |
| [device/main.py](device/main.py)         | entry point: WiFi, refresh pacing, touch, LEDs      |
| [device/config.py](device/config.py)     | position, radius, credentials, units, brightness    |
| [device/netapi.py](device/netapi.py)     | the HTTP calls, OAuth2 tokens and credit accounting |
| [device/flights.py](device/flights.py)   | state vectors, parsed and converted out of metric   |
| [device/geo.py](device/geo.py)           | distance, bearing, bounding box, scope projection   |
| [device/radar.py](device/radar.py)       | screen layout and drawing                           |
| [device/demo.py](device/demo.py)         | synthetic traffic for when the feed is unreachable  |
| [pc/check_access.py](pc/check_access.py) | what will the feed give you, and how often?         |
| [pc/preview.py](pc/preview.py)           | draw the screen to SVG, no board needed             |
| [tests/](tests/)                         | `pytest tests`                                      |

`geo.py`, `flights.py` and `demo.py` are plain Python with no firmware imports,
which is what lets the tests and both `pc/` scripts run them under CPython.

## Things worth knowing

- **The feed is metric, the screen is not.** OpenSky reports altitude in
  metres, speed in m/s and climb rate in m/s;
  [device/flights.py](device/flights.py) converts to the feet and knots
  aviation actually uses.
- **A box, not a circle.** OpenSky filters by bounding box, so a query returns
  up to 27% more sky than asked for and the corners are trimmed off by
  distance. It also returns no range or bearing, so those are computed on the
  device.
- **Resolution.** Runs at 480x480. Measured on hardware at about 6fps with
  contacts drawn, against roughly 10 at 240x240 - and since the data only
  changes every 30 seconds, that frame rate governs nothing but how quickly a
  tap registers. `FULL_RES = False` in [device/config.py](device/config.py)
  gives the snappier 240x240; the layout is drawn from `display.get_bounds()`
  and scales either way.
- **Fonts.** Uses the built-in bitmap font out of the box. Copy
  [`Roboto-Medium.af`](https://github.com/pimoroni/presto/blob/main/examples/Roboto-Medium.af)
  to the device for nicer antialiased text - it's picked up automatically.
- **Units.** Distance follows `DISTANCE_UNITS` (`nm`, `km` or `mi`). Altitude is
  always feet and speed always knots, because that is what aviation uses and
  what the feed reports.
- **Nothing on screen?** The status bar carries the reason: `no wifi`,
  `no location`, `429 - out of credits`, `401 - check credentials`. A `DEMO`
  prefix means what you are watching is synthetic.
- **A quiet sky is not a fault.** `NO AIRCRAFT IN RANGE` at 3am over a rural
  county is the correct answer. Widen `RADIUS_NM` to check.

## Resetting the board while it is drawing

Nothing here is firmware-specific, but one habit will cost you an afternoon.
A soft reset (ctrl-D, or `mpremote soft-reset`) does not release the display:
the DMA and the PSRAM framebuffer are held by the C module, not by the
Python object. Soft-resetting out of a session that has a live `Presto` and
then constructing a new one wedges the board hard enough that it stops
servicing USB, and only the reset button gets it back.

So when a test has built a `Presto`, hard reset - `machine.reset()`, or the
button - before building another. `mpremote run` and `mpremote exec` share one
interpreter across invocations, which makes this easier to hit than it sounds.

If a board does wedge and `main.py` runs on boot, it will wedge again a few
seconds after every reset. Recover by hammering ctrl-C through the boot window
and renaming `main.py` before it gets that far.

## Keep a reference to the PicoVector transform

`PicoVector.set_transform()` keeps only a raw pointer to the `Transform` you
hand it. Passing a temporary:

```python
vector.set_transform(Transform())      # wrong: nothing holds it
```

leaves the object unreferenced, and once the garbage collector takes it every
subsequent text draw reads freed memory. It does not raise. What it does
instead depends on what lands in the freed block: attributes vanish from live
objects, module globals turn into unrelated values, tracebacks name qstrs that
were never involved, and sometimes the board hangs outright. The symptoms move
around as the heap layout changes, which makes it look like flaky hardware.

[device/radar.py](device/radar.py) binds it to `self.transform`, as every
Presto example does. Worth knowing about if you write another of these.

## Prototype scope

A scope, a countdown and one aircraft's details - the fields the layout is
built around. OpenSky's other endpoints carry more: `/tracks` would give the
selected aircraft's recent trajectory for a trail, and `/flights/arrival` would
say where something is going. Both cost far more credits than `/states/all`, so
neither is here. Trails, an airline lookup for the callsign prefix and a
tap-to-zoom range control are the obvious next things.
