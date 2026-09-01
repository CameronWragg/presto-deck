# presto-deck

Projects for the [Pimoroni Presto](https://github.com/pimoroni/presto) - a
480x480 touchscreen with RGB ambient lighting, running MicroPython on an
RP2350.

## Projects

| Project                                      | What it does                                                            |
| -------------------------------------------- | ----------------------------------------------------------------------- |
| [simhub-dashboard](simhub-dashboard/)        | Sim racing dashboard: speed, RPM, gear and shift lights fed from SimHub over local WiFi. |

Each project is self-contained: a `device/` directory to copy onto the Presto,
plus whatever host-side tooling and docs it needs. Run its commands from inside
the project directory.

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
