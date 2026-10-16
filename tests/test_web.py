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


class RelayTests(unittest.TestCase):
    """A web pod following a real scanner and a real Wi-Fi watch server."""

    def setUp(self):
        from overwatch.wifi import WifiWatch

        self.watch, self.wifi = Watch(learn_seconds=0, started=0), WifiWatch()
        self.watch.scanning = self.wifi.scanning = True
        hubs = Hub(), Hub()
        self.scanner_url, stop1 = serve(scanner_server(self.watch, hubs[0], "127.0.0.1", 0, heartbeat=0.2))
        self.wifi_url, stop2 = serve(scanner_server(self.wifi, hubs[1], "127.0.0.1", 0, heartbeat=0.2))
        self.addCleanup(stop1)
        self.addCleanup(stop2)
        self.wifi_hub = hubs[1]

    def test_both_feeds_reach_the_page_and_a_threat_arrives_live(self):
        from overwatch.wifi import Network, parse
        from tests.test_wifi import OTHER_AP, beacon

        hub = Hub()
        relay = web.Relay([("scanner", self.scanner_url), ("wifi", self.wifi_url)], hub, timeout=1, retry=0.05)
        base, stop = serve(web.make_server(relay, hub, "127.0.0.1", 0, heartbeat=0.2))
        self.addCleanup(stop)
        threading.Thread(target=relay.run, daemon=True).start()
        deadline = time.time() + 3
        while time.time() < deadline and not (relay.ready and relay.feed("wifi").ready):
            time.sleep(0.01)
        _, st = get_json(base + "/api/state")
        self.assertEqual([f["name"] for f in st["feeds"]], ["scanner", "wifi"])
        wifi = st["feeds"][1]
        self.assertEqual((wifi["error"], wifi["state"]["threats"], wifi["state"]["panel"]["rows"]), ("", [], []))
        self.wifi.home = [Network("home", "Castle", set(), "WPA2", set())]
        self.wifi.heard(parse(beacon(OTHER_AP, "Castle")), -40, 6)
        self.wifi_hub.publish(state(self.wifi))
        deadline = time.time() + 3
        while time.time() < deadline:
            _, st = get_json(base + "/api/state")
            if st["feeds"][1]["state"]["threats"]:
                break
            time.sleep(0.01)
        panel = st["feeds"][1]["state"]["panel"]
        self.assertEqual(st["feeds"][1]["state"]["threats"][0]["kind"], "twin")
        self.assertEqual((panel["headline"]["severity"], panel["rows"][0]["verdict"]["tone"]), (3, "bad"))

    def test_ready_without_a_wifi_watch(self):
        hub = Hub()
        relay = web.Relay([("scanner", self.scanner_url), ("wifi", "http://127.0.0.1:9")], hub, timeout=1, retry=0.05)
        threading.Thread(target=relay.run, daemon=True).start()
        deadline = time.time() + 3
        while time.time() < deadline and not (relay.ready and relay.feed("wifi").error):
            time.sleep(0.01)
        self.assertTrue(relay.ready)
        self.assertEqual(json.loads(hub.latest())["feeds"][1]["error"], "wifi unreachable")

    def test_a_new_feed_drops_in(self):
        """A feed the relay has never heard of, with any name, passes straight
        through: its panel is all the page needs (#12)."""
        from overwatch.hub import Hub as H

        class Radar:  # a made-up fourth watch, in the common shape
            scanning, error = True, ""

            def get(self):
                return {"error": "", "alerts": []}

            def panel(self, st):
                return {"id": "radar", "title": "Radar", "icon": "radar", "status": {"state": "ok", "text": "sweeping"},
                        "headline": {"severity": 0, "word": "ALL CLEAR", "tone": "ok", "line": ""},
                        "stats": [], "meta": "", "columns": [{"label": "What"}],
                        "rows": [{"key": "a", "name": "Blip", "cells": []}], "empty": "", "alerts": []}

        radar_hub = H()
        radar_url, stop3 = serve(scanner_server(Radar(), radar_hub, "127.0.0.1", 0, heartbeat=0.2))
        self.addCleanup(stop3)
        radar_hub.publish(state(Radar()))
        hub = Hub()
        relay = web.Relay([("scanner", self.scanner_url), ("radar", radar_url)], hub, timeout=1, retry=0.05)
        threading.Thread(target=relay.run, daemon=True).start()
        deadline = time.time() + 3
        while time.time() < deadline and not (relay.ready and relay.feed("radar").ready):
            time.sleep(0.01)
        radar = json.loads(hub.latest())["feeds"][1]
        self.assertEqual((radar["name"], radar["state"]["panel"]["rows"][0]["name"]), ("radar", "Blip"))


class FeedListTests(unittest.TestCase):
    def test_parse_feeds(self):
        self.assertEqual(web.parse_feeds(" scanner=http://a , wifi=http://b,"), [("scanner", "http://a"), ("wifi", "http://b")])
        for bad in ("", "scanner", "=http://a", "a=http://x,a=http://y"):
            with self.assertRaises(ValueError):
                web.parse_feeds(bad)

    def test_the_older_variables_still_work(self):
        from overwatch.__main__ import web_feeds

        self.assertEqual(web_feeds({"OVERWATCH_SCANNER_URL": "http://s", "OVERWATCH_UPNP_URL": "http://u"}),
                         [("scanner", "http://s"), ("upnp", "http://u")])
        self.assertEqual(web_feeds({"OVERWATCH_FEEDS": "scanner=http://s", "OVERWATCH_WIFI_URL": "http://w"}),
                         [("scanner", "http://s")])
