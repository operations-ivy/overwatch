from __future__ import annotations

import json
import unittest

from overwatch.watch import Watch, classify, describe, uuid16


class ClassifyTests(unittest.TestCase):
    def test_trackers_and_gadgets(self):
        self.assertEqual(classify(None, {0x004C: bytes([0x12, 0x19, 0x10])}, [], {}), "findmy")
        self.assertEqual(classify(None, {}, [uuid16(0xFD5A)], {}), "smarttag")
        self.assertEqual(classify(None, {}, [], {uuid16(0xFEED): b"\x02"}), "tile")
        self.assertEqual(classify(None, {}, [], {uuid16(0xFEAA): b"\x41abc"}), "googletag")
        self.assertEqual(classify(None, {}, [uuid16(0xFD5F)], {}), "meta")
        self.assertEqual(classify("Flipper Zorbo", {}, [], {}), "flipper")
        self.assertEqual(classify(None, {}, [uuid16(0x3082)], {}), "flipperish")
        self.assertEqual(classify("HC-05", {}, [], {}), "skimmer")
        self.assertEqual(classify(None, {}, [], {}, "00:25:df:12:34:56", "public"), "axon")
        self.assertEqual(classify(None, {}, [], {uuid16(0xFFFA): b"\x0d\x01" + bytes(25)}), "drone")
        self.assertEqual(classify(None, {0x0D53: b"\x01"}, [], {}), "meta")
        self.assertEqual(classify(None, {0x03C2: b"\x01"}, [], {}), "spectacles")
        self.assertEqual(classify(None, {0x0E29: b"\x01"}, [], {}), "flipper")
        self.assertEqual(classify(None, {0x004C: b"\x02\x15" + bytes(21)}, [], {}), "ibeacon")

    def test_everyday_devices_are_ignored(self):
        self.assertIsNone(classify(None, {0x004C: bytes([0x10, 0x05])}, [], {}))  # an iPhone's nearby info
        self.assertIsNone(classify("JBL Flip 5", {0x0057: b"\x01"}, [], {}))
        self.assertIsNone(classify(None, {}, [], {uuid16(0xFEAA): b"\x10url"}))  # a plain Eddystone URL beacon
        self.assertIsNone(classify(None, {0x004C: b""}, [], {}))
        self.assertIsNone(classify(None, {}, [], {}, "00:25:DF:12:34:56", "random"))  # a random address, not Axon's
        self.assertIsNone(classify(None, {}, [], {uuid16(0xFFFA): b"\x01"}))  # 0xFFFA, but not Remote ID's app code


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.w = Watch(learn_seconds=600, linger_seconds=120, gone_seconds=120, started=0)

    def heard(self, t, *addresses, kind="findmy", rssi=-60):
        for a in addresses:
            self.w.advert(a, kind, rssi, now=t)
        self.w.tick(now=t)

    def test_the_house_normal_is_learned_and_never_alerts(self):
        for t in range(0, 1200, 10):
            self.heard(t, "AA", "BB")
        self.assertEqual(self.w.normal, {"findmy": 2})
        self.assertEqual(self.w.alerts, [])

    def test_a_newcomer_lingering_past_the_normal_alerts_once(self):
        for t in range(0, 600, 10):
            self.heard(t, "AA")
        for t in range(600, 720, 10):
            self.heard(t, "AA", "CC")
        self.assertEqual(self.w.alerts, [])  # not yet two minutes over
        for t in range(720, 900, 10):
            self.heard(t, "AA", "CC")
        self.assertEqual(len(self.w.alerts), 1)
        a = self.w.alerts[0]
        self.assertEqual((a["kind"], a["count"], a["normal"]), ("findmy", 2, 1))

    def test_a_passer_by_does_not_alert(self):
        for t in range(0, 600, 10):
            self.heard(t, "AA")
        for t in range(600, 660, 10):
            self.heard(t, "AA", "CC")
        for t in range(660, 1000, 10):
            self.heard(t, "AA")
        self.assertEqual(self.w.alerts, [])

    def test_low_confidence_kinds_show_but_never_alert(self):
        for t in range(600, 1200, 10):
            self.heard(t, "DD", kind="flipperish")
        self.assertEqual(self.w.alerts, [])
        self.assertEqual(self.w.get(now=1200)["kinds"][0]["count"], 1)

    def test_devices_drop_off_after_gone_seconds(self):
        self.heard(0, "AA")
        self.assertEqual(self.w.get(now=100)["kinds"][0]["count"], 1)
        self.assertEqual(self.w.get(now=121)["kinds"], [])

    def test_each_kind_reports_its_closest_device(self):
        self.w.advert("AA", "findmy", -80, now=0)
        self.w.advert("BB", "findmy", -55, now=0)
        self.w.advert("CC", "flipper", -70, now=0)
        kinds = {k["kind"]: k for k in self.w.get(now=1)["kinds"]}
        self.assertEqual((kinds["findmy"]["count"], kinds["findmy"]["closest"]), (2, -55))
        self.assertTrue(kinds["findmy"]["tracker"])
        self.assertFalse(kinds["flipper"]["tracker"])

    def test_no_address_reaches_the_state(self):
        self.heard(0, "F0:12:34:56:78:9A", rssi=-70)
        state = json.dumps(self.w.get(now=1))
        self.assertNotIn("F0:12", state)
        self.assertNotIn("56:78", state)
        # Nor even the salted id: only counts per kind.
        self.assertNotIn(self.w._key("F0:12:34:56:78:9A"), state)


class DescribeTests(unittest.TestCase):
    def test_find_my_battery_and_makers(self):
        d = describe("findmy", None, {0x004C: bytes([0x12, 0x19, 0b10_000000]) + b"\x00" * 22}, [], {})
        self.assertEqual((d["battery"], d["makers"]), ("low", ["Apple"]))

    def test_google_tag_away_from_its_owner(self):
        self.assertEqual(describe("googletag", None, {}, [], {uuid16(0xFEAA): b"\x41k"})["mode"], "away from its owner")
        self.assertEqual(describe("googletag", None, {}, [], {uuid16(0xFEAA): b"\x40k"})["mode"], "near its owner")

    def test_names_services_and_power(self):
        d = describe("flipper", "Flipper Zorbo", {0x9999: b"x"}, [uuid16(0x3082), uuid16(0x1234)], {}, tx_power=4)
        self.assertEqual(d["name"], "Flipper Zorbo")
        self.assertEqual(d["tx_power"], 4)
        self.assertEqual(d["makers"], ["0x9999"])
        self.assertEqual(d["services"], ["0x1234", "Flipper-like (0x3082)"])

    def test_no_raw_payloads(self):
        key = bytes(range(30, 52))
        d = describe("findmy", None, {0x004C: bytes([0x12, 0x19, 0]) + key}, [], {})
        self.assertNotIn(key.hex(), json.dumps(d))
        self.assertEqual(set(d), {"makers", "battery"})


class DeviceDetailTests(unittest.TestCase):
    def test_each_device_is_numbered_with_its_signal_range_and_advert_count(self):
        w = Watch(started=0)
        w.advert("F0:12:34:56:78:9A", "tile", -80, now=0, details={"makers": ["0x00ED"]}, address_type="random")
        w.advert("F0:12:34:56:78:9A", "tile", -60, now=5)
        w.advert("BB", "tile", -90, now=6)
        devices = w.get(now=6)["kinds"][0]["devices"]
        self.assertEqual([d["n"] for d in devices], [1, 2])  # strongest first
        first = devices[0]
        self.assertEqual((first["rssi"], first["rssi_min"], first["rssi_max"]), (-60, -80, -60))
        self.assertEqual((first["first"], first["last"], first["adverts"]), (0, 5, 2))
        self.assertEqual((first["address_type"], first["makers"]), ("random", ["0x00ED"]))
        self.assertNotIn("F0:12", json.dumps(w.get(now=6)))
