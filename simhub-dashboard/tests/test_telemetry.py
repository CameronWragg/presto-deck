#!/usr/bin/env python3
"""Tests for the parts of the device code that run under CPython too.

    python3 tests/test_telemetry.py
"""

import os
import socket
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "device"))

from demo import DemoCar  # noqa: E402
from netlink import LineBuffer, LineLink  # noqa: E402
from telemetry import Telemetry  # noqa: E402


class TestParsing(unittest.TestCase):
    def setUp(self):
        self.tel = Telemetry(default_max_rpm=8000)

    def test_full_message(self):
        self.assertTrue(self.tel.update("$SH|SPD=123|RPM=6543|MAX=7800|GEAR=4", 0))
        self.assertEqual(self.tel.speed_kmh, 123)
        self.assertEqual(self.tel.rpm, 6543)
        self.assertEqual(self.tel.max_rpm, 7800)
        self.assertEqual(self.tel.gear, "4")

    def test_bytes_and_whitespace(self):
        self.assertTrue(self.tel.update(b"  $SH|SPD=80|RPM=3000\r\n", 0))
        self.assertEqual(self.tel.speed_kmh, 80)

    def test_partial_update_keeps_previous_values(self):
        self.tel.update("$SH|SPD=100|RPM=5000|MAX=7000|GEAR=3", 0)
        self.tel.update("$SH|SPD=105", 10)
        self.assertEqual(self.tel.speed_kmh, 105)
        self.assertEqual(self.tel.rpm, 5000)
        self.assertEqual(self.tel.gear, "3")

    def test_unknown_keys_ignored(self):
        self.assertTrue(self.tel.update("$SH|SPD=50|FUEL=12.3|TYRE=hard", 0))
        self.assertEqual(self.tel.speed_kmh, 50)

    def test_marker_optional(self):
        self.assertTrue(self.tel.update("SPD=50|RPM=1000", 0))
        self.assertEqual(self.tel.speed_kmh, 50)

    def test_junk_counted_not_applied(self):
        self.assertFalse(self.tel.update("hello there", 0))
        self.assertEqual(self.tel.packets, 0)
        self.assertEqual(self.tel.bad_packets, 1)

    def test_decimal_comma_locale(self):
        self.tel.update("$SH|SPD=123,5", 0)
        self.assertAlmostEqual(self.tel.speed_kmh, 123.5)

    def test_zero_max_rpm_ignored(self):
        self.tel.update("$SH|MAX=7500", 0)
        self.tel.update("$SH|MAX=0", 1)  # games report 0 before the car loads
        self.assertEqual(self.tel.max_rpm, 7500)

    def test_neutral_gear_forms(self):
        self.tel.update("$SH|GEAR=0", 0)
        self.assertEqual(self.tel.gear, "N")
        self.tel.update("$SH|GEAR=R", 1)
        self.assertEqual(self.tel.gear, "R")


class TestDerived(unittest.TestCase):
    def setUp(self):
        self.tel = Telemetry(default_max_rpm=8000, shift_flash=0.97)

    def test_units(self):
        self.tel.update("$SH|SPD=100", 0)
        self.assertAlmostEqual(self.tel.speed("kmh"), 100)
        self.assertAlmostEqual(self.tel.speed("mph"), 62.1371)

    def test_rev_fraction_clamped(self):
        self.tel.update("$SH|RPM=9000|MAX=8000", 0)
        self.assertEqual(self.tel.rev_fraction, 1.0)
        self.assertTrue(self.tel.shifting)

    def test_shift_point_from_absolute_rpm(self):
        self.tel.update("$SH|MAX=8000|SLI=7200", 0)
        self.assertAlmostEqual(self.tel.shift_point, 0.9)

    def test_staleness(self):
        self.assertFalse(self.tel.is_live(0, 1500))
        self.tel.update("$SH|SPD=10", 1000)
        self.assertTrue(self.tel.is_live(2000, 1500))
        self.assertFalse(self.tel.is_live(3000, 1500))


class TestLineBuffer(unittest.TestCase):
    def test_reassembles_split_lines(self):
        buffer, out = LineBuffer(), []
        buffer.feed(b"$SH|SPD=1", out)
        self.assertEqual(out, [])
        buffer.feed(b"0\n$SH|SPD=20\n$SH|SP", out)
        self.assertEqual(out, [b"$SH|SPD=10", b"$SH|SPD=20"])

    def test_drops_overlong_garbage(self):
        buffer, out = LineBuffer(), []
        buffer.feed(b"x" * 600, out)
        buffer.feed(b"$SH|SPD=5\n", out)
        self.assertEqual(out, [b"$SH|SPD=5"])


class TestLink(unittest.TestCase):
    """End to end: the wire protocol into telemetry state."""

    def test_udp_and_tcp(self):
        link = LineLink(tcp_port=5123, udp_port=5124)
        self.assertEqual(link.errors, [])
        tel = Telemetry()

        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.sendto(b"$SH|SPD=88|RPM=4000|MAX=7000\n", ("127.0.0.1", 5124))
        tcp = socket.create_connection(("127.0.0.1", 5123))
        tcp.sendall(b"$SH|GEAR=3\n")
        time.sleep(0.2)

        for line in link.poll():
            tel.update(line, 0)
        tcp.close()
        udp.close()
        link.close()

        self.assertEqual(tel.packets, 2)
        self.assertEqual(tel.speed_kmh, 88)
        self.assertEqual(tel.gear, "3")


class TestDemoCar(unittest.TestCase):
    def test_produces_parsable_lines_and_uses_the_rev_range(self):
        car, tel = DemoCar(), Telemetry()
        peak, gears = 0.0, set()
        for _ in range(400):
            self.assertTrue(tel.update(car.step(50), 0))
            peak = max(peak, tel.rev_fraction)
            gears.add(tel.gear)
        self.assertGreater(peak, 0.9)
        self.assertGreater(len(gears), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
