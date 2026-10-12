from __future__ import annotations

import unittest

from overwatch import web
from overwatch.scanner import make_server as scanner_server
from overwatch.watch import Watch
from tests.helpers import get, get_json, serve


class WebTests(unittest.TestCase):
    """A web pod against a real scanner HTTP server (with a fake radio)."""

    def setUp(self):
        self.watch = Watch(learn_seconds=0, started=0)
        self.watch.scanning = True
        self.watch.advert("AA", "tile", -70)
        self.scanner_url, self.stop_scanner = serve(scanner_server(self.watch, "127.0.0.1", 0))
        self.poller = web.Poller(self.scanner_url, timeout=1)
        self.base, stop = serve(web.make_server(self.poller, "127.0.0.1", 0))
        self.addCleanup(stop)

    def tearDown(self):
        self.stop_scanner()  # idempotent enough: shutdown on a stopped server returns

    def test_not_ready_until_the_first_answer(self):
        self.assertEqual(get(self.base + "/health")[0], 200)
        self.assertEqual(get(self.base + "/ready")[0], 503)
        self.poller.poll_once()
        self.assertEqual(get(self.base + "/ready")[0], 200)
        status, state = get_json(self.base + "/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(state["error"], "")
        self.assertEqual(state["scanner"]["kinds"][0]["kind"], "tile")

    def test_keeps_the_last_answer_and_stays_ready_when_the_scanner_goes(self):
        self.poller.poll_once()
        fetched = self.poller.fetched
        self.stop_scanner()
        self.poller.poll_once()
        status, state = get_json(self.base + "/api/state")
        self.assertEqual(state["error"], "scanner unreachable")
        self.assertEqual(state["fetched"], fetched)
        self.assertEqual(state["scanner"]["kinds"][0]["kind"], "tile")
        self.assertEqual(get(self.base + "/ready")[0], 200)

    def test_never_ready_if_the_scanner_never_answered(self):
        self.stop_scanner()
        self.poller.poll_once()
        self.assertEqual(get(self.base + "/ready")[0], 503)
        self.assertIsNone(get_json(self.base + "/api/state")[1]["scanner"])

    def test_serves_the_page(self):
        status, body = get(self.base + "/")
        self.assertEqual(status, 200)
        self.assertIn(b"<title>overwatch", body)
