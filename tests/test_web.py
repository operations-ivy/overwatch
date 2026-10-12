import json
import os
import socket
import subprocess
import sys
import threading
import time
import unittest
import urllib.request

from overwatch import web
from overwatch.hub import Hub, events
from overwatch.scanner import make_server as scanner_server
from overwatch.scanner import state
from overwatch.watch import Watch
from tests.helpers import get, get_json, serve


class WebTests(unittest.TestCase):
    """A web pod following a real scanner HTTP server (with a fake radio)."""

    def setUp(self):
        self.watch, self.scanner_hub = Watch(learn_seconds=0, started=0), Hub()
        self.watch.scanning = True
        self.scanner_url, self.stop_scanner = serve(
            scanner_server(self.watch, self.scanner_hub, "127.0.0.1", 0, heartbeat=0.2)
        )
        self.hub = Hub()
        self.upstream = web.Upstream(self.scanner_url, self.hub, timeout=1, retry=0.05)
        self.base, stop = serve(web.make_server(self.upstream, self.hub, "127.0.0.1", 0, heartbeat=0.2))
        self.addCleanup(stop)

    def tearDown(self):
        self.stop_scanner()

    def follow(self):
        threading.Thread(target=self.upstream.run, daemon=True).start()

    def wait_for(self, check, timeout=3):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if check():
                return True
            time.sleep(0.01)
        return False

    def test_not_ready_until_the_first_state(self):
        self.assertEqual(get(self.base + "/health")[0], 200)
        self.assertEqual(get(self.base + "/ready")[0], 503)
        self.follow()
        self.assertTrue(self.wait_for(lambda: get(self.base + "/ready")[0] == 200))
        status, st = get_json(self.base + "/api/state")
        self.assertEqual((status, st["error"]), (200, ""))
        self.assertEqual(st["scanner"]["kinds"], [])

    def test_an_advert_reaches_the_browser_stream_within_100_ms(self):
        self.follow()
        self.assertTrue(self.wait_for(lambda: self.upstream.ready))
        with urllib.request.urlopen(self.base + "/api/stream", timeout=5) as r:
            feed = (json.loads(e) for e in events(r) if e is not None)
            next(feed)  # the state now
            start = time.monotonic()
            self.watch.advert("AA", "tile", -70)  # what on_advert does
            self.scanner_hub.publish(state(self.watch))
            st = next(feed)
            elapsed = time.monotonic() - start
        self.assertEqual(st["scanner"]["kinds"][0]["kind"], "tile")
        self.assertLess(elapsed, 0.1)

    def test_says_so_and_stays_ready_when_the_scanner_dies(self):
        # A real scanner process (no Bluetooth here, so it reports that), killed
        # mid-stream the way a pod dies: its sockets close under the web pod.
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        env = {**os.environ, "OVERWATCH_PORT": str(port)}
        proc = subprocess.Popen(
            [sys.executable, "-m", "overwatch", "scan"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        self.addCleanup(proc.kill)
        self.upstream.url = f"http://127.0.0.1:{port}/api/stream"
        self.follow()
        self.assertTrue(self.wait_for(lambda: self.upstream.ready, timeout=10))
        proc.kill()
        proc.wait(5)
        self.assertTrue(self.wait_for(lambda: get_json(self.base + "/api/state")[1]["error"] == "scanner unreachable"))
        self.assertIsNotNone(get_json(self.base + "/api/state")[1]["scanner"])  # what it last said
        self.assertEqual(get(self.base + "/ready")[0], 200)

    def test_never_ready_if_the_scanner_never_answered(self):
        self.stop_scanner()
        self.upstream.follow_once()
        self.assertEqual(get(self.base + "/ready")[0], 503)
        self.assertIsNone(get_json(self.base + "/api/state")[1]["scanner"])

    def test_serves_the_page(self):
        status, body = get(self.base + "/")
        self.assertEqual(status, 200)
        self.assertIn(b"<title>overwatch", body)
        self.assertIn(b'new EventSource("/api/stream")', body)
