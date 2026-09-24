# OpenDoist V1 — local Todoist-compatible clone

Free, local-first Todoist (web) clone: vanilla HTML/JS/CSS UI + Todoist API v1-compatible
local API for Omarchy plugins. No account, no paywall.

> **Disclaimer:** Not created by, affiliated with, or supported by Todoist.

## Run

```bash
OPENDOIST_DB=~/.local/share/opendoist/opendoist.db uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000/` (Today / Inbox / Upcoming + quick-add).
Bind ONLY `127.0.0.1:8000` — never `0.0.0.0`. `GET /health` → `{"ok": true}`.

## Auth

Single local user. Any non-empty Bearer token works:

```
Authorization: Bearer <anything>
```

Missing/empty token → `401 {"error_tag":"UNAUTHORIZED","error_code":477,...}`.
All data is scoped to `user_id=1`.

## API quick tour

- `POST /api/v1/tasks/quick` — EN quick-add (`Buy milk tomorrow #Shopping @errands p1`);
  bare text defaults due **today** server-side; accepts + ignores `auto_reminder`;
  honors `X-Request-Id` idempotency.
- `POST /api/v1/sync` — form-encoded Sync read/write (`sync_token="*"`, `resource_types`
  JSON, `commands[]` with per-`uuid` idempotency, `temp_id_mapping`).
- `GET /api/v1/tasks/filter?query=` — `today`, `overdue`, `today | overdue`, `inbox`,
  `#Project`, `@label`/`%label`, `p1..p4` (p1 = priority 4).
- REST: `POST/GET /api/v1/tasks`, `GET/POST/DELETE /api/v1/tasks/{id}`,
  `POST .../close|reopen|move`; projects/sections/labels CRUD + archive flags.
- Priority mapping: `p1→4, p2→3, p3→2, p4→1`, both directions.

## Scope

V1 (this repo state) ships the core task flow in tier order:

- **V1-T0** Foundation: FastAPI monolith, SQLite WAL, auth, `GET /health`.
- **V1-T1** Daily-usable: task CRUD, EN quick-add parser, minimal web UI, minimal sync read.
- **V1-T2** Organization + full omatasks compat: projects/sections/labels, filter/search,
  due times + timezones, Smart sort, full sync read+write, reorder + duplicate.
- **V1-T3** Pixel polish + validation: Todoist-style UI, screenshot compare,
  omatasks-fork validation vs localhost, this gate (`tests/test_plugin_compat.py`).

The **complete app** (full Todoist parity, Teams included) is REQUIRED post-V1 and is
tracked as backlog tiers **C-T1..C-T5** in order — see
`zenno/specs/2026-09-19-opendoist-design.md` §2:

- **C-T1** Task depth (subtasks, recurrence, reminders CRUD, comments, uploads…)
- **C-T2** Views & productivity (filters CRUD, Board+Calendar, history, karma…)
- **C-T3** Collaboration & Teams (workspaces, roles, invites, full resource_types…)
- **C-T4** Platform & flagship (OAuth, multi-user, backups, webhooks, Docker, FR NLP…)
- **C-T5** Omarchy (maintained patched fork of omatasks ONLY — no omarchy-todoist fork)

## Pointing omatasks at localhost

See `omatasks-fork.patch.md` for the fork patch (configurable base URL,
default `http://localhost:8000/api/v1`).

## Tests

```bash
python -m pytest -q
```

## Languages (quick-add dates)
EN + FR ship with parity. Add a language in 3 steps: 1) create `app/nlp/<code>.py` with `find_dates(text, today) -> {due_date, due_datetime, spans}`, 2) `register("<code>", module)` in `app/nlp/__init__.py` (+ detect markers if auto-detect should find it), 3) add `tests/test_nlp_<code>.py` mirroring the parity table.
