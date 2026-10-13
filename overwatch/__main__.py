"""Run one half of overwatch:

    python -m overwatch scan               the scanner (needs the host's D-Bus socket)
    python -m overwatch wifi               the Wi-Fi watch (needs a monitor-mode dongle)
    python -m overwatch wifi-survey [60]   print a draft house-networks file from what it hears
    python -m overwatch web                a web pod (needs OVERWATCH_SCANNER_URL)

Settings come from the environment: OVERWATCH_PORT (8080), OVERWATCH_LEARN_SECONDS
(600, scanner), OVERWATCH_WIFI_IFACE (wlmon0), OVERWATCH_WIFI_HOME (the house
networks' JSON), OVERWATCH_WIFI_HOME_SHARE (0.6, time on their channels),
OVERWATCH_SCANNER_URL and OVERWATCH_WIFI_URL (web; no Wi-Fi panel without it).
"""

from __future__ import annotations

import logging
import os
import sys

from . import scanner, web, wifi


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
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
    elif mode == "web":
        web.main(
            "0.0.0.0",
            port,
            os.environ.get("OVERWATCH_SCANNER_URL", "http://overwatch-scanner"),
            os.environ.get("OVERWATCH_WIFI_URL", ""),
        )
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
