# The Draw

The Draw is a solo-first random drawing room built with FastAPI, Jinja, plain
JavaScript, SQLAlchemy, and WebSockets. Start a fair server-side draw by
yourself, then share the same room when other people need to join.

It supports inclusive number ranges, pasted or weighted lists, coins, and dice.
Rooms keep their configuration, remaining no-replacement pool, result history,
and concise audit receipts across reloads and reconnects. There are no
popularity counters or client-generated results.

## Product behavior

- Random choices use Python's `secrets` module on the server. Number/list draws
  without replacement persist their remaining pool in the database.
- Each draw stores its index, actor, timestamp, result, eligible-pool count, and
  a SHA-256 fingerprint of the eligible pool before selection. The fingerprint
  is useful audit data; it is not proof of publicly verifiable randomness.
- A room has a six-character share code and a separate internal UUID. A
  room-scoped host token controls settings, reset, invalidation, and ending.
- Drawing can be host-only or open to anyone. Invalidation appends an audit event
  and can return the latest result to the current round; it never rewrites
  history silently.
- New rooms expire after 30 days. A host may end one earlier. Existing V1 rooms
  remain accessible and do not receive a retroactive expiry.
- English and Spanish are handled by the small translation dictionary in
  `app/static/js/i18n.js`; the browser remembers the selected language.

## Local development

Python 3.11 is the deployed runtime.

```sh
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
DATABASE_URL=sqlite:///./random_draw.db .venv/bin/uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. `GET /health` should return
`{"status":"healthy"}`.

The default database is `./random_draw.db`. Use a disposable path for tests,
smoke runs, and manual UAT. Never copy host tokens into source control or logs;
they are room-scoped credentials returned only when a room is created.

## Database migration and V1 compatibility

Application startup runs the same additive, idempotent migration as:

```sh
DATABASE_URL=sqlite:///./random_draw.db .venv/bin/python migrate_db.py
```

The migration leaves the original `rooms` and `logs` tables and columns in
place, adds nullable V2 state columns, creates `room_events`, and adds the unique
short-code index. Legacy room mode and numeric settings are inferred from the V1
columns; legacy rooms default to active and anyone-can-draw. Their short code is
assigned lazily and persisted on first V2 access. Existing logs are preserved.

Legacy rooms predate host credentials, so they remain usable for draws but do
not gain host-only management authority automatically. Creating an ad hoc host
token for an old room would weaken the permission model and is intentionally not
part of the migration.

Back up a persistent database before any release migration. SQLite and
PostgreSQL use the same `create_tables()` migration path; `postgres://` URLs are
normalized to SQLAlchemy's `postgresql://` form.

## HTTP and WebSocket API

Every room endpoint accepts either the internal UUID or short code as
`{room}`. Host actions accept `X-Host-Token: <token>` or
`Authorization: Bearer <token>`. Participant-safe responses never include the
host token or its stored hash.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/rooms` | Create a room and return state plus the one-time host token |
| `GET` | `/api/rooms/{room}` | Get canonical configuration, pool counts, history, and permissions |
| `GET` | `/api/rooms/lookup/{code}` | Resolve a human-friendly short code |
| `PATCH` | `/api/rooms/{room}` | Host: change mode/configuration or draw policy |
| `POST` | `/api/rooms/{room}/draw` | Draw `count` results according to persisted room state |
| `POST` | `/api/rooms/{room}/reset` | Host: start a fresh round |
| `POST` | `/api/rooms/{room}/invalidate` | Host: invalidate the latest current-round result |
| `POST` | `/api/rooms/{room}/end` | Host: end the room |
| `GET` | `/api/rooms/{room}/export?format=json\|csv` | Export result/audit history |
| `GET` | `/api/rooms/{room}/qr.svg` | Get an SVG QR code for the participant share URL |

Create a no-replacement number room:

```sh
curl -sS http://127.0.0.1:8000/api/rooms \
  -H 'content-type: application/json' \
  -d '{
    "mode":"numbers",
    "config":{"min":1,"max":20,"with_replacement":false,"draw_count":1},
    "draw_policy":"host_only",
    "host_name":"Referee"
  }'
```

Mode configuration shapes are:

```json
{
  "numbers": {"min": 1, "max": 100, "with_replacement": false, "draw_count": 1},
  "list": {"list_text": "Ada, Grace\nLinus :: 3", "with_replacement": false, "draw_count": 3, "presentation": "order"},
  "coin": {"draw_count": 1},
  "dice": {"dice_count": 2, "dice_sides": 6, "draw_count": 1}
}
```

List text accepts line breaks, commas, and tabs. Matching is case-insensitive for
deduplication and preserves the first spelling/order. `Name :: 3` assigns a
positive whole-number weight. Structured clients may instead send
`items: [{"value":"Name","weight":3}]`. List presentation is `plain`,
`winner`, `order`, or `teams`; teams also carries `team_count` from 2 to 20.
Order and teams return one flat canonical randomized result array, with the
presentation metadata retained in state/history so every client can render the
same ordering or round-robin team split after reconnect.

Connect realtime clients at:

```text
ws://127.0.0.1:8000/ws/room/{room}?client_id={stable-id}&name={display-name}
```

The server first sends `{"type":"state","state":...}` and broadcasts a full
canonical state after presence or room changes. Send `heartbeat`, `name_change`,
`draw`, `update_settings`, `reset`, `invalidate`, or `end` messages. Browser
hosts should authenticate with an initial
`{"type":"auth","host_token":"..."}` message. The token is deliberately not
accepted in the WebSocket URL, so it does not enter browser history or ordinary
server access logs. Errors are structured `type: error` messages and do not
close a healthy connection.

## CLI/API smoke path

The standard-library CLI exercises the same API used by the UI. Commands cover
create, state, draw, configure, reset, invalidate, end, JSON/CSV export, and QR
download:

```sh
python scripts/random_draw_smoke.py --help
python scripts/random_draw_smoke.py create --mode dice \
  --config '{"dice_count":2,"dice_sides":6,"draw_count":1}'
RANDOM_DRAW_HOST_TOKEN='<room-scoped token>' \
  python scripts/random_draw_smoke.py draw ABC123 --actor 'CLI host'
```

With the app running on a disposable local database, run the mutating end-to-end
scenario:

```sh
python scripts/random_draw_smoke.py \
  --base-url http://127.0.0.1:8000 smoke
```

The scenario creates and ends a room while checking health, short-code lookup,
no-replacement exhaustion, invalidation, reset, configuration/permission update,
history export, and QR generation. Do not run it against production.

## Verification

```sh
.venv/bin/python -m pytest -q
```

Manual desktop, mobile, sharing, reconnect, localization, and accessibility
acceptance cases are in [`docs/UAT.md`](docs/UAT.md). Use a disposable local
database for the checklist.

## Deployment boundary

This repository's GitHub Actions workflow tests pull requests and deploys pushes
to `main` on the `randomenumbers` self-hosted runner, with a local health check
and rollback attempt. Normal production releases go through that workflow.

Do not push a feature branch, merge to `main`, run a local provider deploy,
change DNS/tunnel routing, or mutate the production database without separate
explicit approval. Local development, migration tests against copied data, and
the smoke path do not require production access.

## Repository map

- `app/main.py` — application setup, health endpoint, and lifecycle
- `app/models/database.py` — V1-compatible models and additive migrations
- `app/services/drawing.py` — validation, authoritative drawing, receipts, state
- `app/routers/rooms.py` — HTML compatibility routes and REST API
- `app/routers/websocket.py` — presence, reconnect, and realtime actions
- `app/templates/`, `app/static/` — Jinja pages, tabletop theme, and plain JS
- `scripts/random_draw_smoke.py` — external CLI/API verification path
- `tests/` — unit and HTTP/WebSocket integration coverage
- `docs/UAT.md` — manual acceptance checklist

## License

MIT
