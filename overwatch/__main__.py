"""Run one half of overwatch:

    python -m overwatch scan    the scanner (needs the host's D-Bus socket)
    python -m overwatch web     a web pod (needs OVERWATCH_SCANNER_URL)

Settings come from the environment: OVERWATCH_PORT (8080), OVERWATCH_LEARN_SECONDS
(600, scanner), OVERWATCH_SCANNER_URL (web).
"""

from __future__ import annotations

import logging
import os
import sys

from . import scanner, web


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    port = int(os.environ.get("OVERWATCH_PORT", "8080"))
    if mode == "scan":
        scanner.main("0.0.0.0", port, float(os.environ.get("OVERWATCH_LEARN_SECONDS", "600")))
    elif mode == "web":
        web.main("0.0.0.0", port, os.environ.get("OVERWATCH_SCANNER_URL", "http://overwatch-scanner"))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
