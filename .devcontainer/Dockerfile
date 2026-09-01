# Development container for presto-deck.
#
# The Pimoroni Presto runs MicroPython on an RP2350; none of this Python
# actually executes in here. What the container is for is the host side of
# the work: linting, the CPython-compatible tests, the pc/ bridge scripts,
# and mpremote talking to the board over USB.
FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

# The base image ships a yarn apt source whose signing key no longer verifies
# (NO_PUBKEY 62D54FD4003F6525), which fails `apt-get update` outright. Nothing
# here is a node project, so drop the repo rather than chase the key.
RUN rm -f /etc/apt/sources.list.d/yarn.list

# picocom for a raw serial console when mpremote's REPL isn't enough;
# usbutils/libusb for identifying the board when it enumerates as RP2350.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        libusb-1.0-0 \
        picocom \
        usbutils \
    && rm -rf /var/lib/apt/lists/*

# The Presto shows up as a USB CDC device (/dev/ttyACM0) owned by whichever
# group the host uses for serial ports - dialout (20) on Debian/Ubuntu, uucp
# (984) on Arch. The container user needs to be in the *host's* group, by GID,
# and that has to happen at build time: supplementary groups are fixed when a
# process starts, so adding them later doesn't reach the running shells.
# Override with --build-arg / devcontainer.json if your host differs.
ARG SERIAL_GID=984
RUN if ! getent group "${SERIAL_GID}" > /dev/null; then \
        groupadd --gid "${SERIAL_GID}" hostserial; \
    fi \
    && usermod -aG "$(getent group "${SERIAL_GID}" | cut -d: -f1)",dialout vscode

COPY requirements-dev.txt /tmp/requirements-dev.txt
RUN pip install --no-cache-dir -r /tmp/requirements-dev.txt
