"""Run one half of overwatch:

    python -m overwatch scan               the scanner (needs the host's D-Bus socket)
    python -m overwatch wifi               the Wi-Fi watch (needs a monitor-mode dongle)
    python -m overwatch wifi-survey [60]   print a draft house-networks file from what it hears
    python -m overwatch upnp               the UPnP watch (needs the LAN: host network)
    python -m overwatch web                a web pod (needs OVERWATCH_SCANNER_URL)

Settings come from the environment: OVERWATCH_PORT (8080), OVERWATCH_LEARN_SECONDS
(600, scanner), OVERWATCH_WIFI_IFACE (wlmon0), OVERWATCH_WIFI_HOME (the house
networks' JSON), OVERWATCH_WIFI_HOME_SHARE (0.6, time on their channels),
OVERWATCH_UPNP_ROUTER (192.168.1.1), OVERWATCH_UPNP_ALLOW (allowed forwards),
OVERWATCH_UPNP_INTERVAL (60), and for the web pods OVERWATCH_FEEDS
(`scanner=http://...,wifi=http://...,upnp=http://...`: every feed, in page
order, the first required; or the older OVERWATCH_SCANNER_URL, _WIFI_URL
and _UPNP_URL).
"""

from __future__ import annotations

import os
import sys

import brick_observe

from . import scanner, upnp, web, wifi


def web_feeds(env) -> list[tuple[str, str]]:
    """OVERWATCH_FEEDS (name=url,...; the first is required), or the older
    OVERWATCH_SCANNER_URL / _WIFI_URL / _UPNP_URL."""
    if env.get("OVERWATCH_FEEDS", "").strip():
        return web.parse_feeds(env["OVERWATCH_FEEDS"])
    feeds = [("scanner", env.get("OVERWATCH_SCANNER_URL", "http://overwatch-scanner"))]
    for name, var in (("wifi", "OVERWATCH_WIFI_URL"), ("upnp", "OVERWATCH_UPNP_URL")):
        if env.get(var):
            feeds.append((name, env[var]))
    return feeds


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    brick_observe.init(f"overwatch-{mode or 'cli'}")
    port = int(os.environ.get("OVERWATCH_PORT", "8080"))
    if mode == "scan":
        scanner.main("0.0.0.0", port, float(os.environ.get("OVERWATCH_LEARN_SECONDS", "600")))
    elif mode == "wifi":
        wifi.main(
            "0.0.0.0",
            port,
            os.environ.get("OVERWATCH_WIFI_IFACE", "wlmon0"),
            os.environ.get("OVERWATCH_WIFI_HOME", ""),
            float(os.environ.get("OVERWATCH_WIFI_HOME_SHARE", "0.6")),
        )
    elif mode == "wifi-survey":
        wifi.survey(os.environ.get("OVERWATCH_WIFI_IFACE", "wlmon0"), float(sys.argv[2]) if len(sys.argv) > 2 else 60)
    elif mode == "upnp":
        upnp.main(
            "0.0.0.0",
            port,
            os.environ.get("OVERWATCH_UPNP_ROUTER", "192.168.1.1"),
            os.environ.get("OVERWATCH_UPNP_ALLOW", ""),
            float(os.environ.get("OVERWATCH_UPNP_INTERVAL", "60")),
        )
    elif mode == "web":
        web.main("0.0.0.0", port, web_feeds(os.environ))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
