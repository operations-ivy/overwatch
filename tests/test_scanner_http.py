import unittest
import urllib.request

from overwatch.hub import Hub, events
from overwatch.scanner import make_server, state
from overwatch.watch import Watch
from tests.helpers import get, get_json, serve


class ScannerHttpTests(unittest.TestCase):
    def setUp(self):
        self.watch, self.hub = Watch(learn_seconds=600, started=0), Hub()
        self.base, stop = serve(make_server(self.watch, self.hub, "127.0.0.1", 0, heartbeat=0.2))
        self.addCleanup(stop)

    def test_ready_only_while_bluez_is_scanning(self):
        self.assertEqual(get(self.base + "/health")[0], 200)
        self.assertEqual(get(self.base + "/ready")[0], 503)
        self.watch.scanning = True
        self.assertEqual(get(self.base + "/ready")[0], 200)

    def test_state_has_counts_per_kind_and_no_addresses(self):
        self.watch.advert("F0:12:34:56:78:9A", "findmy", -58)
        self.watch.scanning = True
        status, st = get_json(self.base + "/api/state")
        self.assertEqual(status, 200)
        self.assertTrue(st["scanning"])
        self.assertEqual(st["kinds"][0]["kind"], "findmy")
        self.assertEqual(st["kinds"][0]["closest"], -58)
        self.assertNotIn("F0:12", str(st))

    def test_stream_sends_the_state_at_once_then_each_change(self):
        with urllib.request.urlopen(self.base + "/api/stream", timeout=5) as r:
            feed = (e for e in events(r) if e is not None)
            self.assertIn(b'"kinds": []', next(feed))
            self.watch.advert("AA", "tile", -70)
            self.hub.publish(state(self.watch))
            self.assertIn(b'"tile"', next(feed))

    def test_unknown_paths_are_404(self):
        self.assertEqual(get(self.base + "/nope")[0], 404)
