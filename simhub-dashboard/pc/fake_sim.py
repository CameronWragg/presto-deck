#!/usr/bin/env python3
"""Pretend to be SimHub, so you can test the Presto dashboard on its own.

Sends the same protocol the real bridge sends, driving a synthetic car round
the rev range.

    python fake_sim.py --host 192.168.1.42
    python fake_sim.py --host 192.168.1.42 --tcp --rate 20
    python fake_sim.py --print                 # just show the protocol lines
"""

import argparse
import os
import socket
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "device"))

from demo import DemoCar  # noqa: E402 - needs the path above


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", help="Presto's IP address")
    parser.add_argument("--port", type=int, default=5005)
    parser.add_argument("--tcp", action="store_true", help="use TCP instead of UDP")
    parser.add_argument("--rate", type=float, default=20.0, help="updates per second")
    parser.add_argument("--print", dest="show", action="store_true",
                        help="print lines instead of sending them")
    args = parser.parse_args()

    if not args.host and not args.show:
        parser.error("--host is required (or use --print)")

    sock = None
    if not args.show:
        if args.tcp:
            sock = socket.create_connection((args.host, args.port), timeout=5)
        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        print("Sending to {}:{} over {} at {}Hz".format(
            args.host, args.port, "TCP" if args.tcp else "UDP", args.rate))

    car = DemoCar()
    interval = 1.0 / args.rate
    try:
        while True:
            line = car.step(interval * 1000) + "\n"
            if args.show:
                print(line, end="")
            elif args.tcp:
                sock.sendall(line.encode("ascii"))
            else:
                sock.sendto(line.encode("ascii"), (args.host, args.port))
            time.sleep(interval)
    except KeyboardInterrupt:
        if sock is not None:
            sock.close()
        return 0


if __name__ == "__main__":
    sys.exit(main())
