"""Stubs for `ezwifi`, the WiFi helper frozen into the Presto firmware.

Written against presto v2.0.0 (modules/py_frozen/ezwifi.py).
https://github.com/pimoroni/presto/blob/main/docs/wifi.md
"""

from typing import Any, Callable

class LogLevel:
    INFO: int
    WARNING: int
    ERROR: int

class EzWiFi:
    def __init__(self, **kwargs: Any) -> None: ...
    def on(
        self, handler_name: str, handler: Callable[..., Any] | None = None
    ) -> Callable[..., Any]:
        """Register a connected/failed/info/warning/error callback."""

    def error(self) -> tuple[int | None, str | None]:
        """(status code, name) of the last failure."""

    async def connect(
        self,
        ssid: str | None = None,
        password: str | None = None,
        timeout: int = 60,
        retries: int = 10,
    ) -> bool: ...
    def ipv4(self) -> str:
        """Our address, as a string. A method, not a property - call it."""

    def ipv6(self) -> str: ...
    def isconnected(self) -> bool: ...

def connect(**kwargs: Any) -> bool:
    """Module-level blocking connect using secrets.py."""
