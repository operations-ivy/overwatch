import json
import threading
import unittest

from overwatch.hub import Hub, events, stream


class HubTests(unittest.TestCase):
    def test_publishes_only_changes_and_stamps_them(self):
        hub = Hub()
        self.assertTrue(hub.publish({"a": 1}))
        self.assertFalse(hub.publish({"a": 1}))
        self.assertTrue(hub.publish({"a": 2}))
        state = json.loads(hub.latest())
        self.assertEqual(state["a"], 2)
        self.assertIn("changed", state)

    def test_a_waiting_listener_wakes_on_publish(self):
        hub, got = Hub(), []
        listener = threading.Thread(target=lambda: got.append(hub.wait(0, 5)))
        listener.start()
        hub.publish({"a": 1})
        listener.join(5)
        self.assertEqual(got[0][0], 1)

    def test_a_slow_listener_skips_to_the_latest(self):
        hub = Hub()
        for n in range(5):
            hub.publish({"n": n})
        version, data = hub.wait(0, 1)
        self.assertEqual((version, json.loads(data)["n"]), (5, 4))

    def test_heartbeat_when_nothing_changes(self):
        hub, out = Hub(), []
        hub.publish({"a": 1})

        def write(chunk):
            out.append(chunk)
            if len(out) == 2:
                raise BrokenPipeError

        with self.assertRaises(BrokenPipeError):
            stream(hub, write, heartbeat=0.05)
        self.assertTrue(out[0].startswith(b"data: "))
        self.assertEqual(out[1], b": ping\n\n")

    def test_parses_events_and_heartbeats(self):
        lines = [b'data: {"a": 1}\n', b"\n", b": ping\n", b"\n", b"data: x\r\n", b"\r\n"]
        self.assertEqual(list(events(lines)), [b'{"a": 1}', None, b"x"])
