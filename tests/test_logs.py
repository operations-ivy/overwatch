import io
import json

import brick_observe

from overwatch import scanner, upnp, watch, web, wifi


def test_every_module_logs_one_json_object_with_the_standard_fields():
    stream = io.StringIO()
    brick_observe.init("overwatch-test", json=True, tracing_enabled=False, stream=stream)
    for module in (scanner, upnp, watch, web, wifi):
        module.log.info("skipping channel", channel=13)
    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert [line["logger"] for line in lines] == [m.__name__ for m in (scanner, upnp, watch, web, wifi)]
    for line in lines:
        assert line["event"] == "skipping channel"
        assert line["channel"] == 13
        assert line["level"] == "info"
        assert line["service"] == "overwatch-test"
        assert line["timestamp"]
