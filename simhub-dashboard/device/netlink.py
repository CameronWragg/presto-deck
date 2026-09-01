"""Non-blocking line-oriented telemetry sources for the Presto.

Everything here is polled from the render loop and never blocks, so a missing
or wedged PC can't stall the dashboard.

    link = LineLink(tcp_port=5005, udp_port=5005)
    for line in link.poll():
        telemetry.update(line, time.ticks_ms())
"""

import errno
import socket

_EAGAIN = (
    getattr(errno, "EAGAIN", 11),
    getattr(errno, "EWOULDBLOCK", 11),
    getattr(errno, "ETIMEDOUT", 110),
)

# Longest run of bytes we'll hold while waiting for a newline. SimHub messages
# are tens of bytes; anything longer means we're out of sync, so drop it.
MAX_LINE = 512


class LineBuffer:
    """Splits a byte stream into newline terminated lines."""

    def __init__(self):
        self._buf = b""

    def feed(self, data, out):
        self._buf += data
        while True:
            index = self._buf.find(b"\n")
            if index < 0:
                break
            line = self._buf[:index]
            self._buf = self._buf[index + 1:]
            line = line.strip()
            if line:
                out.append(line)
        if len(self._buf) > MAX_LINE:
            self._buf = b""

    def reset(self):
        self._buf = b""


def _split_datagram(data, out):
    for line in data.replace(b"\r", b"\n").split(b"\n"):
        line = line.strip()
        if line:
            out.append(line)


class TcpLineServer:
    """Accepts one client at a time - a serial-over-TCP bridge, typically."""

    name = "tcp"

    def __init__(self, port):
        self.port = port
        self._client = None
        self._buffer = LineBuffer()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("0.0.0.0", port))
        self._sock.listen(1)
        self._sock.setblocking(False)

    @property
    def connected(self):
        return self._client is not None

    def poll(self, out):
        self._accept()
        if self._client is None:
            return
        while True:
            try:
                data = self._client.recv(256)
            except OSError as error:
                if error.args and error.args[0] in _EAGAIN:
                    return
                self._drop()
                return
            if not data:  # peer closed
                self._drop()
                return
            self._buffer.feed(data, out)
            if len(data) < 256:
                return

    def _accept(self):
        try:
            client, _address = self._sock.accept()
        except OSError as error:
            if error.args and error.args[0] in _EAGAIN:
                return
            return
        client.setblocking(False)
        if self._client is not None:
            # Last bridge to connect wins, so a reconnecting PC isn't locked out.
            self._drop()
        self._client = client
        self._buffer.reset()

    def close(self):
        self._drop()
        try:
            self._sock.close()
        except OSError:
            pass

    def _drop(self):
        if self._client is not None:
            try:
                self._client.close()
            except OSError:
                pass
        self._client = None
        self._buffer.reset()


class UdpLineReceiver:
    """Fire-and-forget datagrams, one or more lines per packet."""

    name = "udp"

    def __init__(self, port):
        self.port = port
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("0.0.0.0", port))
        self._sock.setblocking(False)

    def poll(self, out):
        while True:
            try:
                data, _address = self._sock.recvfrom(512)
            except OSError as error:
                if error.args and error.args[0] in _EAGAIN:
                    return
                return
            if not data:
                return
            _split_datagram(data, out)

    def close(self):
        try:
            self._sock.close()
        except OSError:
            pass


class UsbSerialSource:
    """Telemetry over the Presto's own USB serial port.

    Lets SimHub write straight to the board's COM port with no WiFi bridge,
    at the cost of the REPL: ctrl-c no longer interrupts, so use the reset
    button to get the board back.
    """

    name = "usb"

    def __init__(self):
        import micropython
        import select
        import sys

        self._stdin = sys.stdin.buffer
        self._buffer = LineBuffer()
        self._poll = select.poll()
        self._poll.register(self._stdin, select.POLLIN)
        micropython.kbd_intr(-1)  # stop ctrl-c in the data stream killing us

    def poll(self, out):
        while self._poll.poll(0):
            data = self._stdin.read(64)
            if not data:
                return
            self._buffer.feed(data, out)


class LineLink:
    """All enabled sources behind one poll()."""

    def __init__(self, tcp_port=None, udp_port=None, usb=False):
        self.sources = []
        self.errors = []
        if tcp_port:
            self._add(TcpLineServer, tcp_port)
        if udp_port:
            self._add(UdpLineReceiver, udp_port)
        if usb:
            self._add(UsbSerialSource)

    def _add(self, factory, *args):
        try:
            self.sources.append(factory(*args))
        except Exception as error:  # noqa: BLE001 - a dead source must not stop the rest
            self.errors.append("{}: {}".format(factory.__name__, error))

    def poll(self):
        lines = []
        for source in self.sources:
            try:
                source.poll(lines)
            except Exception as error:  # noqa: BLE001
                self.errors.append("{}: {}".format(source.name, error))
        return lines

    def close(self):
        for source in self.sources:
            closer = getattr(source, "close", None)
            if closer:
                closer()
        self.sources = []

    def describe(self):
        return ", ".join(
            "{}:{}".format(source.name, getattr(source, "port", "-"))
            for source in self.sources
        )
