"""Tweakables for the Presto SimHub dashboard.

Copy this file (and the rest of device/) to the root of your Presto.
"""

# --- Display -----------------------------------------------------------------
# full_res=True gives a crisp 480x480 but roughly halves the frame rate.
# The dashboard lays itself out from display.get_bounds(), so both work.
FULL_RES = False

# Target frame rate. The screen is only redrawn when something changed,
# so this is an upper bound, not a busy loop.
TARGET_FPS = 30

# Screen brightness, 0.0 - 1.0.
BACKLIGHT = 1.0

# --- Telemetry link ----------------------------------------------------------
# The device listens on both at once; use whichever suits your bridge.
#   TCP  - for serial-over-TCP bridges (HW VSP3, Perle TruePort, pc/simhub_bridge.py --tcp)
#   UDP  - for pc/simhub_bridge.py (default) and pc/fake_sim.py
TCP_PORT = 5005
UDP_PORT = 5005

# Read telemetry from the USB serial port as well as WiFi.
# Lets SimHub talk to the Presto's own COM port with no bridge at all, BUT it
# takes over the REPL: Thonny/mpremote can no longer interrupt the running
# program, so you have to press the reset button to get the board back.
ENABLE_USB_SERIAL = False

# Treat telemetry as lost after this many milliseconds of silence.
STALE_MS = 1500

# --- Car ---------------------------------------------------------------------
# Used until SimHub tells us the real values (MAX=...).
DEFAULT_MAX_RPM = 8000

# Fraction of max RPM where the shift lights start / go solid red.
SHIFT_START = 0.80
SHIFT_FLASH = 0.97

# "kmh" or "mph" at startup. Tap the screen to toggle.
UNITS = "mph"

# --- Extras ------------------------------------------------------------------
# Mirror the rev lights onto Presto's 7 ambient LEDs.
AMBIENT_REV_LIGHTS = True

# Show a synthetic lap when no telemetry is arriving, handy for checking the
# layout without a PC attached.
DEMO_WHEN_IDLE = True

# Use PicoVector text if a .af font is present on the device (nicer, slower).
# Falls back to the built-in bitmap font automatically.
VECTOR_FONT = "Roboto-Medium.af"
