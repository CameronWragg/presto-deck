"""Tests for the parts of the device code that run under CPython too.

    pytest tests

conftest.py puts the device modules on sys.path.
"""

import socket
import time

import pytest

from demo import DemoCar
from netlink import LineBuffer, LineLink
from telemetry import Telemetry


@pytest.fixture
def tel():
    return Telemetry(default_max_rpm=8000)


class TestParsing:
    def test_full_message(self, tel):
        assert tel.update("$SH|SPD=123|RPM=6543|MAX=7800|GEAR=4", 0)
        assert tel.speed_kmh == 123
        assert tel.rpm == 6543
        assert tel.max_rpm == 7800
        assert tel.gear == "4"

    def test_bytes_and_whitespace(self, tel):
        assert tel.update(b"  $SH|SPD=80|RPM=3000\r\n", 0)
        assert tel.speed_kmh == 80

    def test_partial_update_keeps_previous_values(self, tel):
        tel.update("$SH|SPD=100|RPM=5000|MAX=7000|GEAR=3", 0)
        tel.update("$SH|SPD=105", 10)
        assert tel.speed_kmh == 105
        assert tel.rpm == 5000
        assert tel.gear == "3"

    def test_unknown_keys_ignored(self, tel):
        assert tel.update("$SH|SPD=50|FUEL=12.3|TYRE=hard", 0)
        assert tel.speed_kmh == 50

    def test_marker_optional(self, tel):
        assert tel.update("SPD=50|RPM=1000", 0)
        assert tel.speed_kmh == 50

    def test_junk_counted_not_applied(self, tel):
        assert not tel.update("hello there", 0)
        assert tel.packets == 0
        assert tel.bad_packets == 1

    def test_decimal_comma_locale(self, tel):
        tel.update("$SH|SPD=123,5", 0)
        assert tel.speed_kmh == pytest.approx(123.5)

    def test_zero_max_rpm_ignored(self, tel):
        tel.update("$SH|MAX=7500", 0)
        tel.update("$SH|MAX=0", 1)  # games report 0 before the car loads
        assert tel.max_rpm == 7500

    def test_neutral_gear_forms(self, tel):
        tel.update("$SH|GEAR=0", 0)
        assert tel.gear == "N"
        tel.update("$SH|GEAR=R", 1)
        assert tel.gear == "R"


class TestDerived:
    @pytest.fixture
    def tel(self):
        return Telemetry(default_max_rpm=8000, shift_flash=0.97)

    def test_units(self, tel):
        tel.update("$SH|SPD=100", 0)
        assert tel.speed("kmh") == pytest.approx(100)
        assert tel.speed("mph") == pytest.approx(62.1371)

    def test_rev_fraction_clamped(self, tel):
        tel.update("$SH|RPM=9000|MAX=8000", 0)
        assert tel.rev_fraction == 1.0
        assert tel.shifting

    def test_shift_point_from_absolute_rpm(self, tel):
        tel.update("$SH|MAX=8000|SLI=7200", 0)
        assert tel.shift_point == pytest.approx(0.9)

    def test_staleness(self, tel):
        assert not tel.is_live(0, 1500)
        tel.update("$SH|SPD=10", 1000)
        assert tel.is_live(2000, 1500)
        assert not tel.is_live(3000, 1500)


class TestLineBuffer:
    def test_reassembles_split_lines(self):
        buffer, out = LineBuffer(), []
        buffer.feed(b"$SH|SPD=1", out)
        assert out == []
        buffer.feed(b"0\n$SH|SPD=20\n$SH|SP", out)
        assert out == [b"$SH|SPD=10", b"$SH|SPD=20"]

    def test_drops_overlong_garbage(self):
        buffer, out = LineBuffer(), []
        buffer.feed(b"x" * 600, out)
        buffer.feed(b"$SH|SPD=5\n", out)
        assert out == [b"$SH|SPD=5"]


class TestLink:
    """End to end: the wire protocol into telemetry state."""

    def test_udp_and_tcp(self):
        link = LineLink(tcp_port=5123, udp_port=5124)
        assert link.errors == []
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

        assert tel.packets == 2
        assert tel.speed_kmh == 88
        assert tel.gear == "3"


class TestDemoCar:
    def test_produces_parsable_lines_and_uses_the_rev_range(self):
        car, tel = DemoCar(), Telemetry()
        peak, gears = 0.0, set()
        for _ in range(400):
            assert tel.update(car.step(50), 0)
            peak = max(peak, tel.rev_fraction)
            gears.add(tel.gear)
        assert peak > 0.9
        assert len(gears) > 3
