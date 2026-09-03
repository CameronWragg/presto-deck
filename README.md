# presto-deck

Projects for the [Pimoroni Presto](https://github.com/pimoroni/presto) - a
480x480 touchscreen with RGB ambient lighting, running MicroPython on an
RP2350.

## Projects

| Project                                 | What it does                                                                                |
| --------------------------------------- | ------------------------------------------------------------------------------------------- |
| [simhub-dashboard](simhub-dashboard/)   | Sim racing dashboard: speed, RPM, gear and shift lights fed from SimHub over local WiFi.      |
| [flight-tracker](flight-tracker/)       | Radar scope of the aircraft overhead, from the OpenSky Network's ADS-B feed.                   |

Each project is self-contained: a `device/` directory to copy onto the Presto,
plus whatever host-side tooling and docs it needs. Run its commands from inside
the project directory.

## Development container

`.devcontainer/` sets up everything the host side of a Presto project needs -
Python 3.12, `mpremote`, `pyserial`, `ruff`, and type stubs for the firmware's
built-in modules, so `presto`, `picographics` and `picovector` resolve in the
editor. Open the repo in VS Code and choose *Reopen in Container*.

The container binds `/dev` and runs privileged so the board can be unplugged,
reset and re-enumerated without recreating it. Serial access is by group ID,
which has to be baked in at build time - set `SERIAL_GID` in
[.devcontainer/devcontainer.json](.devcontainer/devcontainer.json) to the group
that owns `/dev/ttyACM0` on your host (984/`uucp` on Arch, 20/`dialout` on
Debian and Ubuntu) and rebuild. USB passthrough is Linux-only; on macOS or
Windows use the container for tests, linting and the `pc/` scripts, and run
`mpremote` on the host.

```
mpremote devs                        # is the board there?
mpremote cp device/*.py :            # deploy, from a project directory
mpremote                             # REPL; ctrl-] to get out
ruff check .
pytest                               # every project's tests, from the root
```

Stubs live in [typings/](typings/) and track a firmware version - see
[typings/README.md](typings/README.md).

## Working with a Presto

- Flash the [Presto MicroPython firmware](https://github.com/pimoroni/presto/releases)
  (hold BOOT, tap RESET, drop the `.uf2` on the USB drive that appears).
- Copy code with Thonny, or `mpremote cp device/*.py :` from a project
  directory. `main.py` runs automatically on reset.
- WiFi comes from a `secrets.py` in the device root - see any project's
  `device/secrets.py.example`. It's gitignored.
- Useful references: [presto module](https://github.com/pimoroni/presto/blob/main/docs/presto.md),
  [EzWiFi](https://github.com/pimoroni/presto/blob/main/docs/wifi.md),
  [PicoVector](https://github.com/pimoroni/presto/blob/main/docs/picovector.md),
  [examples](https://github.com/pimoroni/presto/tree/main/examples).
