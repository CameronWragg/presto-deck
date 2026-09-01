# SimHub Dashboard

A speed/RPM dashboard for the [Pimoroni Presto](https://github.com/pimoroni/presto),
fed from [SimHub](https://www.simhubdash.com/) over local WiFi.

```
┌────────────────────────────────────┐
│ ██████████████░░░░░░░░░░░░░░░░░░░░ │  rev bar, green → amber → red,
│                                    │  flashes blue at the shift point
│              137                   │  speed, tap the screen for km/h
│              MPH                   │
│  ┌──────┐  ┌──────────────────┐    │
│  │  4   │  │ RPM        6543  │    │
│  └──────┘  │ / 7800           │    │
│            └──────────────────┘    │
│ ● SIMHUB 30 fps                    │
└────────────────────────────────────┘
```

The 7 ambient LEDs mirror the rev bar, so the whole unit lights up on the
shift.

## Quick start

Paths and commands below are relative to this directory (`simhub-dashboard/`).

1. Flash the [Presto MicroPython firmware](https://github.com/pimoroni/presto/releases)
   if you haven't already.
2. Copy everything in [device/](device/) to the root of the Presto (Thonny, or
   `mpremote cp device/*.py :`), plus a `secrets.py` with your WiFi details -
   see [device/secrets.py.example](device/secrets.py.example).
3. Reset the board. It connects to WiFi, shows its IP address, and starts a
   demo lap while it waits for telemetry.
4. Check the network path without touching SimHub:

   ```
   python pc/fake_sim.py --host <presto-ip>
   ```

5. Wire up SimHub: [simhub/README.md](simhub/README.md).

## How the telemetry gets there

SimHub's Custom Serial Devices plugin writes to a COM port and nothing else -
there is no network output - so WiFi means handing SimHub a virtual COM port
and forwarding it:

```
SimHub ──► virtual COM ──► pc/simhub_bridge.py ──► UDP/TCP ──► Presto
```

[simhub/README.md](simhub/README.md) covers three routes: com0com plus the
included bridge script (free, easiest to debug), a serial-over-TCP virtual COM
driver talking straight to the device, or a plain USB cable with no WiFi at all.

## Protocol

One ASCII line per update, pipe separated, newline terminated:

```
$SH|SPD=137|RPM=6543|MAX=7800|GEAR=4
```

| Key    | Meaning                                         |
| ------ | ----------------------------------------------- |
| `SPD`  | speed in km/h (the device converts to mph)      |
| `RPM`  | current engine RPM                              |
| `MAX`  | max/redline RPM, scales the rev bar             |
| `GEAR` | gear as text - `N`, `R`, `1`, `2` …             |
| `SLI`  | optional shift point, 0-1 fraction or abs. RPM  |
| `PIT`  | optional, `1` while in the pit lane             |

The `$SH` marker is optional, unknown keys are ignored, and missing keys keep
their last value - so you can extend the SimHub message without touching the
firmware.

## Layout

| Path                                       | What it is                                        |
| ------------------------------------------ | ------------------------------------------------- |
| [device/main.py](device/main.py)           | entry point: WiFi, poll loop, touch, LEDs         |
| [device/config.py](device/config.py)       | ports, units, brightness, shift points, demo mode |
| [device/telemetry.py](device/telemetry.py) | protocol parsing and car state                    |
| [device/netlink.py](device/netlink.py)     | non-blocking TCP / UDP / USB serial sources       |
| [device/dashboard.py](device/dashboard.py) | screen layout and drawing                         |
| [device/demo.py](device/demo.py)           | synthetic car for the idle demo                   |
| [pc/simhub_bridge.py](pc/simhub_bridge.py) | virtual COM port → device                         |
| [pc/fake_sim.py](pc/fake_sim.py)           | fake telemetry sender for testing                 |
| [tests/test_telemetry.py](tests/test_telemetry.py) | `python3 tests/test_telemetry.py`         |

## Things worth knowing

- **Update rate.** The free SimHub build caps custom serial messages at 10Hz.
  The dashboard renders at up to 30fps regardless, so the numbers just step
  ten times a second.
- **Resolution.** Runs at 240x240 by default for frame rate; set
  `FULL_RES = True` in [device/config.py](device/config.py) for a crisp 480x480
  at roughly half the speed. The layout scales either way.
- **Fonts.** Uses the built-in bitmap font out of the box. Copy
  [`Roboto-Medium.af`](https://github.com/pimoroni/presto/blob/main/examples/Roboto-Medium.af)
  to the device for nicer antialiased digits - it's picked up automatically.
- **Units.** Tap anywhere on the screen to swap mph ↔ km/h. Change the startup
  default with `UNITS` in the config.
- **Nothing on screen?** The status bar shows the device's IP and the ports it
  is listening on. If it says `DEMO`, no telemetry is arriving: check the
  bridge is running, that the IP matches, and that Windows Firewall isn't
  eating outbound UDP.

## Prototype scope

Speed, RPM, gear and shift lights only - the fields the layout is built
around. Lap times, fuel, tyres, flags and delta are all a matter of extending
the SimHub message and adding a panel; the parser already ignores what it
doesn't recognise.
