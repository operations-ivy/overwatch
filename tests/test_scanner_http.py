from __future__ import annotations

import unittest

from overwatch.scanner import make_server
from overwatch.watch import Watch
from tests.helpers import get, get_json, serve


class ScannerHttpTests(unittest.TestCase):
    def setUp(self):
        self.watch = Watch(learn_seconds=600, started=0)
        self.base, stop = serve(make_server(self.watch, "127.0.0.1", 0))
        self.addCleanup(stop)

    def test_ready_only_while_bluez_is_scanning(self):
        self.assertEqual(get(self.base + "/health")[0], 200)
        self.assertEqual(get(self.base + "/ready")[0], 503)
        self.watch.scanning = True
        self.assertEqual(get(self.base + "/ready")[0], 200)

    def test_state_has_counts_per_kind_and_no_addresses(self):
        self.watch.advert("F0:12:34:56:78:9A", "findmy", -58)
        self.watch.scanning = True
        status, state = get_json(self.base + "/api/state")
        self.assertEqual(status, 200)
        self.assertTrue(state["scanning"])
        self.assertEqual(state["kinds"][0]["kind"], "findmy")
        self.assertEqual(state["kinds"][0]["closest"], -58)
        self.assertNotIn("F0:12", str(state))

    def test_unknown_paths_are_404(self):
        self.assertEqual(get(self.base + "/nope")[0], 404)
