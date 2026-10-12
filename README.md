# overwatch

Watches Bluetooth LE around the house for trackers and surveillance gadgets,
and shows what it hears at `https://overwatch.brick.nozdormu.cloud`. It's the
brick homelab's take on wigle-sync#35 (inspired by SquachWatch-CYD); it
started as a view on brick1982's arena panel (brick-cicd-config#64).

## What it recognises

Each kind has a confidence; only high and medium ones raise alerts.

| Kind | How it's recognised | Confidence |
| --- | --- | --- |
| Apple Find My tag | Apple manufacturer data, offline-finding type `0x12` | high |
| Samsung SmartTag | service `0xFD5A` | high |
| Tile tracker | services `0xFEED` / `0xFEEC` | high |
| Google Find My tag | Eddystone frames `0x40` / `0x41` | medium |
| Meta device (glasses?) | service `0xFD5F` | medium |
| Flipper Zero | name `Flipper …` | high |
| Flipper-like service | services `0x3081`–`0x3083` | low |
| Serial BT module (skimmer?) | names `HC-05`, `HC-06`, … | low |

Signatures come from the Bluetooth SIG's assigned numbers and published
protocol notes; which devices to look for follows SquachWatch-CYD, but none of
its data is copied.

Households are full of trackers, so for 10 minutes after each start overwatch
learns the usual count of each kind. After that, a high or medium kind above
its usual count for two minutes raises an alert. Only devices heard in the
last 30 s count towards an alert, so a passer-by doesn't.

## The page

Laid out like wigle-console and the chuck reader (same palette and fonts):

- the state in one word and a sentence: all clear, learning, heads up,
  alert, scanner down or no signal;
- tiles for trackers and gadgets nearby, alerts in the last 30 minutes, and
  whether it's still learning;
- each kind nearby: how many, how many is usual, how close the nearest one
  is, and a verdict (usual, above usual, unsure, learning);
- the last half hour's alerts. A new one flashes the header for a minute.

It's live: nothing polls. Each advert that changes what the page shows is
pushed from the scanner to the web pods to every open browser as it happens
(Server-Sent Events; the test suite holds that path under 100 ms). The
header shows how long ago the last change was. Trackers advertise every
0.1–2 s, so that's how fresh it gets.

## How it runs

One image (`whitepatrick/overwatch`), two roles, in the `overwatch` namespace:

- **`overwatch-scanner`**: one pod, pinned to brick1982. A radio is a place,
  not a replica, so there's exactly one, and a rollout stops the old pod
  first (`Recreate`). It talks to the host's bluetoothd through the D-Bus
  system socket (a `hostPath` mount), so it runs as `nobody` (the bus refuses
  a uid the host doesn't know) with no
  capabilities, a read-only root filesystem and no host network. It
  publishes on every advert that changes the state, and on a one-second tick
  for the clock-driven changes (devices leaving, alerts, the learning
  countdown). Ready while BlueZ is scanning.
- **`overwatch-web`**: two pods spread across nodes, with a
  PodDisruptionBudget (`minAvailable: 1`). They hold no state: each keeps
  one stream open to the scanner and passes each change straight on to its
  browsers, so either replica gives the same page. Ready once the first
  state has arrived, so a rollout keeps the old pods serving until a new one
  has data. After that, a pod stays ready if the scanner goes away (closed
  connection, or 15 s without its 5 s heartbeat) and the page says "no
  signal". When a web pod goes, browsers reconnect to the other on their own.

```
browser ◀─SSE── Caddy (brick9000) ◀── Traefik ◀── overwatch-web ×2 ◀─SSE── overwatch-scanner ◀─D-Bus── bluetoothd (brick1982)
```

| Endpoint | Scanner | Web |
| --- | --- | --- |
| `/` | | the page |
| `/api/stream` | Server-Sent Events: the state now, then each change | the same as `{error, scanner}` |
| `/api/state` | the state once (counts per kind, alerts, learning, error) | `{now, error, scanner}` once |
| `/health` | process up | process up |
| `/ready` | BlueZ scanning | has heard from the scanner |

Settings (environment): `OVERWATCH_PORT` (8080), `OVERWATCH_LEARN_SECONDS` (600,
scanner), `OVERWATCH_SCANNER_URL` (web).

### Privacy

- Device addresses never leave the scanner process: each is hashed with a
  per-start salt to tell devices apart, and only counts and the closest
  signal per kind reach `/api/state`.
- Nothing is stored. A restart forgets everything and learns the house again.

### The host

The scanner node needs bluetoothd running with the radio unblocked
(Raspberry Pi OS starts radios blocked): `sudo rfkill unblock bluetooth`,
which systemd-rfkill then keeps. Check with `bluetoothctl show` (`Powered:
yes`). To listen somewhere else, change the scanner's `nodeSelector`.

## Develop

```sh
poetry install
poetry run pytest          # unit tests, plus both HTTP servers for real
poetry run python -m overwatch web   # OVERWATCH_SCANNER_URL=http://<scanner>
```

## Release

1. Bump `version` in `pyproject.toml` and the image tag in both
   Deployments.
2. Build on brick9000 (native arm64):
   `build-image https://github.com/operations-ivy/overwatch <full commit or branch> whitepatrick/overwatch:<version>`
   (brick-cicd-config `brick9000/build-image`).
3. `kubectl diff -f k8s_config/`, then `kubectl apply -f k8s_config/`.
4. Check: `kubectl -n overwatch get pods -o wide` (one scanner on brick1982,
   two web pods on different nodes, all ready) and the page.
