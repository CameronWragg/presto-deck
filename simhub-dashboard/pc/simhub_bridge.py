#!/usr/bin/env python3
"""Bridge SimHub's custom serial output to the Presto over the network.

SimHub's Custom Serial Devices plugin can only write to a COM port, so on the
PC we hand it one end of a virtual null-modem pair (com0com) and forward
everything that comes out of the other end to the Presto over UDP or TCP.

    SimHub  ->  COM11 | COM12  ->  simhub_bridge.py  ->  WiFi  ->  Presto

Usage:
    python simhub_bridge.py --list
    python simhub_bridge.py --serial COM12 --host 192.168.1.42
    python simhub_bridge.py --serial COM12 --host 192.168.1.42 --tcp --echo

Requires pyserial:  pip install pyserial
"""

import argparse
import socket
import sys
import time

DEFAULT_PORT = 5005
DEFAULT_BAUD = 115200


def list_ports():
    from serial.tools import list_ports as tools

    ports = list(tools.comports())
    if not ports:
        print("No serial ports found.")
    for port in ports:
        print("{:10} {}".format(port.device, port.description))


class Sender:
    """Sends complete telemetry lines to the device."""

    def __init__(self, host, port, use_tcp):
        self.address = (host, port)
        self.use_tcp = use_tcp
        self.sock = None
        self._connect()

    def _connect(self):
        if self.use_tcp:
            self.sock = socket.create_connection(self.address, timeout=5)
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        else:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        print("Sending to {}:{} over {}".format(
            self.address[0], self.address[1], "TCP" if self.use_tcp else "UDP"))

    def send(self, line):
        payload = line if line.endswith(b"\n") else line + b"\n"
        try:
            if self.use_tcp:
                self.sock.sendall(payload)
            else:
                self.sock.sendto(payload, self.address)
        except OSError as error:
            print("Send failed ({}), reconnecting...".format(error))
            self.close()
            time.sleep(1)
            self._connect()

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None


def run(args):
    import serial

    sender = Sender(args.host, args.port, args.tcp)
    lines = 0
    last_report = time.time()

    while True:
        try:
            with serial.Serial(args.serial, args.baud, timeout=1) as port:
                print("Reading {} at {} baud".format(args.serial, args.baud))
                while True:
                    line = port.readline().strip()
                    if not line:
                        continue
                    sender.send(line)
                    lines += 1
                    if args.echo:
                        print(line.decode("ascii", "replace"))
                    now = time.time()
                    if not args.echo and now - last_report >= 5:
                        print("{} lines forwarded ({:.1f}/s)".format(
                            lines, lines / max(1e-6, now - last_report)))
                        lines = 0
                        last_report = now
        except serial.SerialException as error:
            print("Serial error: {} - retrying in 2s".format(error))
            time.sleep(2)
        except KeyboardInterrupt:
            sender.close()
            return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--serial", help="COM port SimHub writes to, e.g. COM12 or /dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    parser.add_argument("--host", help="Presto's IP address")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--tcp", action="store_true", help="use TCP instead of UDP")
    parser.add_argument("--echo", action="store_true", help="print every line forwarded")
    parser.add_argument("--list", action="store_true", help="list serial ports and exit")
    args = parser.parse_args()

    if args.list:
        list_ports()
        return 0
    if not args.serial or not args.host:
        parser.error("--serial and --host are required (or use --list)")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
