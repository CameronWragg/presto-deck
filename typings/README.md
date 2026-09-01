# Stubs

Type stubs for the modules baked into the [Presto
firmware](https://github.com/pimoroni/presto/releases). They exist so editors
and type checkers can follow `from presto import Presto` on a machine that has
no Presto attached - nothing here is imported at runtime, on the host or on the
device.

| Stub                                 | Firmware source                                    |
| ------------------------------------ | -------------------------------------------------- |
| [presto.pyi](presto.pyi)             | `modules/py_frozen/presto.py`                       |
| [ezwifi.pyi](ezwifi.pyi)             | `modules/py_frozen/ezwifi.py`                       |
| [touch.pyi](touch.pyi)               | `modules/py_frozen/touch.py`                        |
| [picographics.pyi](picographics.pyi) | `pimoroni-pico`, C module                           |
| [picovector.pyi](picovector.pyi)     | `pimoroni-pico`, C module                           |
| [time.pyi](time.pyi)                 | MicroPython's `time`, not CPython's                 |

`time.pyi` is the odd one out: it shadows the standard library workspace-wide,
because that is the only way pyright will believe in `time.ticks_ms()` -
`stubPath` outranks typeshed, while `extraPaths` does not. Host-side code
under `pc/` and `tests/` therefore sees MicroPython's `time` as well, so a
CPython-only function like `perf_counter` needs adding to the stub before it
will resolve.

Written against **presto v2.0.0**. The MicroPython standard library as built
for the RP2350 (`machine`, `network`, `micropython`, …) comes from the
`micropython-rp2-rpi_pico2_w-stubs` package instead - see
[requirements-dev.txt](../requirements-dev.txt).

When the firmware moves on, diff against
[modules/py_frozen](https://github.com/pimoroni/presto/tree/main/modules/py_frozen)
and update these by hand.

A thing the stubs are good for catching: `EzWiFi.ipv4` is a *method*, not a
property, so `presto.wifi.ipv4` is a bound method object and
`presto.wifi.ipv4()` is the address string.
