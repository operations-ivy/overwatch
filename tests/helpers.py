from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request


def serve(server):
    """Run a ThreadingHTTPServer on its own thread; returns (base_url, stop)."""
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()

    def stop():
        server.shutdown()
        server.server_close()
        thread.join(5)  # only the thread this helper started

    return f"http://127.0.0.1:{server.server_address[1]}", stop


def get(url):
    """(status, body) for a GET, without raising on 4xx/5xx."""
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def get_json(url):
    status, body = get(url)
    return status, json.loads(body)
