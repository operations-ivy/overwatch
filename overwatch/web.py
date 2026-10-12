"""The web pods: the page at overwatch.brick.nozdormu.cloud and its /api/state.

They hold no Bluetooth and no state of their own: each one polls the scanner
every couple of seconds and serves its last answer, so any replica gives the
same page. Ready once the first answer has arrived, so a rollout keeps the old
pods serving until a new one has something to show. After that a pod stays
ready if the scanner goes away, and the page says the data is stale.

    GET /            the page
    GET /api/state   {now, fetched, error, scanner: <the scanner's state>}
    GET /health      the process is up
    GET /ready       has heard from the scanner at least once
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

log = logging.getLogger(__name__)
PAGE = (Path(__file__).parent / "static" / "index.html").read_bytes()


class Poller:
    def __init__(self, url: str, interval: float = 2, timeout: float = 3):
        self.url, self.interval, self.timeout = url.rstrip("/") + "/api/state", interval, timeout
        self.scanner: dict | None = None
        self.fetched = 0.0
        self.error = ""
        self._lock = threading.Lock()

    def poll_once(self) -> None:
        try:
            with urllib.request.urlopen(self.url, timeout=self.timeout) as r:
                answer = json.load(r)
        except Exception as e:  # scanner restarting, moved, or not up yet
            with self._lock:
                if not self.error:
                    log.warning("scanner unreachable: %s", e)
                self.error = "scanner unreachable"
            return
        with self._lock:
            if self.error:
                log.info("scanner back")
            self.scanner, self.fetched, self.error = answer, time.time(), ""

    def run(self) -> None:
        while True:
            self.poll_once()
            time.sleep(self.interval)

    @property
    def ready(self) -> bool:
        return self.fetched > 0

    def state(self) -> dict:
        with self._lock:
            return {"now": time.time(), "fetched": self.fetched, "error": self.error, "scanner": self.scanner}


def make_server(poller: Poller, host: str, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(200, PAGE, "text/html; charset=utf-8")
            elif self.path == "/api/state":
                self._send(200, json.dumps(poller.state()).encode(), "application/json")
            elif self.path == "/health":
                self._send(200, b"ok\n")
            elif self.path == "/ready":
                self._send(*((200, b"ready\n") if poller.ready else (503, b"no scanner data yet\n")))
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
            pass

    return ThreadingHTTPServer((host, port), Handler)


def main(host: str, port: int, scanner_url: str) -> None:
    poller = Poller(scanner_url)
    threading.Thread(target=poller.run, daemon=True).start()
    log.info("web on %s:%d, polling %s", host, port, poller.url)
    make_server(poller, host, port).serve_forever()
