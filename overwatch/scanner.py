"""The scanner: listens to Bluetooth LE through the host's BlueZ (over the
D-Bus system socket, so the container needs no privileges) and serves what it
hears to the web pods.

There is one scanner, pinned to the node whose radio should listen: it is a
place, not a replica. Its learned normals live in memory, so a restart
learns the house again.

    GET /api/state   counts per kind, alerts, learning, error
    GET /health      the process is up
    GET /ready       BlueZ is scanning
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .watch import Watch, classify

log = logging.getLogger(__name__)


def scan_forever(watch: Watch, retry_seconds: float = 30) -> None:
    """Scan forever (a daemon thread). Without an adapter or bluetoothd, say
    so in the state and keep retrying."""
    from bleak import BleakScanner

    def on_advert(device, adv) -> None:
        kind = classify(adv.local_name, dict(adv.manufacturer_data), list(adv.service_uuids), dict(adv.service_data))
        if kind:
            watch.advert(device.address, kind, adv.rssi)

    async def scan() -> None:
        async with BleakScanner(on_advert):
            watch.error, watch.scanning = "", True
            log.info("scanning")
            while True:
                watch.tick()
                await asyncio.sleep(2)

    while True:
        try:
            asyncio.run(scan())
        except Exception as e:  # no adapter, bluetoothd restarting, socket missing
            watch.error, watch.scanning = "no Bluetooth", False
            log.warning("scan failed: %s", e)
        time.sleep(retry_seconds)


def make_server(watch: Watch, host: str, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/api/state":
                body = {"now": time.time(), "scanning": watch.scanning, **watch.get()}
                self._send(200, json.dumps(body).encode(), "application/json")
            elif self.path == "/health":
                self._send(200, b"ok\n")
            elif self.path == "/ready":
                self._send(*((200, b"scanning\n") if watch.scanning else (503, b"not scanning\n")))
            else:
                self._send(404, b"not found\n")

        def _send(self, code: int, body: bytes, ctype: str = "text/plain; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass  # probes every few seconds; errors still reach the log

    return ThreadingHTTPServer((host, port), Handler)


def main(host: str, port: int, learn_seconds: float) -> None:
    watch = Watch(learn_seconds=learn_seconds)
    threading.Thread(target=scan_forever, args=(watch,), daemon=True).start()
    log.info("scanner on %s:%d", host, port)
    make_server(watch, host, port).serve_forever()
