"""Parsing and state for the SimHub telemetry protocol.

Wire format is one ASCII line per update, pipe separated key=value pairs:

    $SH|SPD=123|RPM=6543|MAX=7800|GEAR=4

The leading `$SH` marker is optional, unknown keys are ignored and missing
keys keep their previous value, so the SimHub-side message can grow without
touching the device.

Recognised keys:
    SPD  speed in km/h            RPM  current engine RPM
    MAX  max/redline RPM          GEAR gear as text: N, R, 1, 2, ...
    SLI  shift point as a 0-1 fraction of MAX (optional)
    PIT  1 while in the pit lane (optional)

This module is deliberately plain Python so it runs under CPython too - see
tests/test_telemetry.py.
"""

KMH_TO_MPH = 0.621371


def _number(text, fallback=None):
    """Parse a SimHub numeric field, tolerating decimal commas and blanks."""
    text = text.strip().replace(",", ".")
    if not text:
        return fallback
    try:
        return float(text)
    except ValueError:
        return fallback


class Telemetry:
    """Latest known car state, fed one protocol line at a time."""

    def __init__(self, default_max_rpm=8000, shift_start=0.80, shift_flash=0.97):
        self.default_max_rpm = default_max_rpm
        self.shift_start = shift_start
        self.shift_flash = shift_flash

        self.speed_kmh = 0.0
        self.rpm = 0.0
        self.max_rpm = default_max_rpm
        self.gear = "N"
        self.in_pit = False

        # Shift point as a fraction of max_rpm, overridden by SLI if SimHub
        # sends the car's real shift light setting.
        self.shift_point = shift_start

        self.packets = 0
        self.bad_packets = 0
        self.last_packet_ms = None

    # -- input ---------------------------------------------------------------

    def update(self, line, now_ms):
        """Apply one line of telemetry. Returns True if it parsed."""
        if isinstance(line, bytes):
            try:
                line = line.decode("ascii")
            except (UnicodeError, ValueError):
                self.bad_packets += 1
                return False

        line = line.strip()
        if not line:
            return False

        applied = False
        for token in line.split("|"):
            if "=" not in token:
                continue  # the "$SH" marker, or padding
            key, _, value = token.partition("=")
            if self._apply(key.strip().upper(), value):
                applied = True

        if not applied:
            self.bad_packets += 1
            return False

        self.packets += 1
        self.last_packet_ms = now_ms
        return True

    def _apply(self, key, value):
        if key == "SPD":
            speed = _number(value)
            if speed is None:
                return False
            self.speed_kmh = speed
        elif key == "RPM":
            rpm = _number(value)
            if rpm is None:
                return False
            self.rpm = rpm
        elif key == "MAX":
            max_rpm = _number(value)
            # Some games report 0 until the car is loaded - keep the old value.
            if max_rpm is None or max_rpm < 100:
                return False
            self.max_rpm = max_rpm
        elif key == "GEAR":
            gear = value.strip().upper()
            if not gear:
                return False
            self.gear = "N" if gear in ("0", "NEUTRAL") else gear
        elif key == "SLI":
            shift = _number(value)
            if shift is None:
                return False
            # Accept either a 0-1 fraction or an absolute RPM.
            if shift > 1.0:
                shift = shift / self.max_rpm if self.max_rpm else self.shift_start
            self.shift_point = min(max(shift, 0.1), 1.0)
        elif key == "PIT":
            self.in_pit = value.strip() not in ("", "0", "False", "false")
        else:
            return False  # unknown key, ignored but not an error on its own
        return True

    # -- derived state -------------------------------------------------------

    def speed(self, units="kmh"):
        return self.speed_kmh * KMH_TO_MPH if units == "mph" else self.speed_kmh

    @property
    def rev_fraction(self):
        """Current RPM as a 0.0 - 1.0 fraction of max RPM."""
        if not self.max_rpm:
            return 0.0
        return min(max(self.rpm / self.max_rpm, 0.0), 1.0)

    @property
    def shifting(self):
        """True once we are past the flash-the-lights point."""
        return self.rev_fraction >= self.shift_flash

    def is_live(self, now_ms, stale_ms):
        if self.last_packet_ms is None:
            return False
        return (now_ms - self.last_packet_ms) < stale_ms

    def reset_car(self):
        self.speed_kmh = 0.0
        self.rpm = 0.0
        self.gear = "N"
        self.in_pit = False
