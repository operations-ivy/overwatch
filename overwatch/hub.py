"""Push: the latest state, handed to every listener the moment it changes.

Each listener waits for a version newer than the one it last saw and gets
the latest snapshot, never a backlog: a slow browser skips straight to now.
Server-Sent Events carry it (`stream`), so browsers reconnect on their own.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator


class Hub:
    def __init__(self):
        self._cond = threading.Condition()
        self._version = 0
        self._data = b""
        self._key = b""
        self.clients = 0  # listeners streaming now

    def publish(self, state: dict) -> bool:
        """Hand `state` to every listener, stamped with `changed` (when it
        changed), unless it's the same as last time."""
        key = json.dumps(state, sort_keys=True).encode()
        with self._cond:
            if key == self._key:
                return False
            self._key = key
            self._data = json.dumps({**state, "changed": time.time()}, sort_keys=True).encode()
            self._version += 1
            self._cond.notify_all()
            return True

    @property
    def version(self) -> int:
        return self._version

    def latest(self) -> bytes:
        with self._cond:
            return self._data

    def wait(self, seen: int, timeout: float) -> tuple[int, bytes]:
        """The first version after `seen`, or (seen, b"") after `timeout`."""
        with self._cond:
            self._cond.wait_for(lambda: self._version > seen, timeout)
            return (self._version, self._data) if self._version > seen else (seen, b"")


def stream(hub: Hub, write, heartbeat: float = 5) -> None:
    """Write `hub`'s states to one client as Server-Sent Events until it goes
    away: the current state at once, then each change, and a comment line
    every `heartbeat` seconds so proxies and the client know it's alive."""
    seen = 0
    with hub._cond:
        hub.clients += 1
    try:
        while True:
            seen, data = hub.wait(seen, heartbeat)
            write(b"data: " + data + b"\n\n" if data else b": ping\n\n")
    finally:
        with hub._cond:
            hub.clients -= 1


def events(lines: Iterator[bytes]) -> Iterator[bytes | None]:
    """Parse an SSE stream: each event's data, or None for a heartbeat."""
    data = []
    for raw in lines:
        line = raw.rstrip(b"\r\n")
        if line.startswith(b"data:"):
            data.append(line[5:].lstrip(b" "))
        elif line.startswith(b":"):
            yield None
        elif not line and data:
            yield b"\n".join(data)
            data = []
