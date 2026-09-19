# OpenDoist — Design Spec (2026-09-19)

> Free, local-first Todoist clone. EN-first UI. Single FastAPI monolith + SQLite.
> Repo: https://github.com/keypaa/todoist-home
> Status: brainstorming approved (Sec 1+2+3 = Looks good). V1 = core flow. Full vision preserved below so we don't forget.

## 1. Goal / Success criteria

Build a free Todoist (web version) clone named **OpenDoist** that:
1. Looks/feels like Todoist web (sidebar: Add task, Search, Inbox, Today, Upcoming, Filters & Labels, Projects; main Today view grouped like screenshot but EN).
2. Exposes a **Todoist API v1-compatible** local API so existing Omarchy plugins work without a Todoist account:
   - https://github.com/crmne/omatasks (uses form-encoded incremental Sync, JSON Quick Add, task close)
   - https://github.com/Aryan-Techie/omarchy-todoist (uses `GET /tasks/filter`, `GET /tasks`, `POST /tasks/quick`, `POST /tasks/{id}`, `POST /tasks/{id}/close`, `DELETE /tasks/{id}`)
3. V1 must pass: web UI manual test + `pytest` API compat + plugin-compat script mimicking both plugins.
4. No paywall, no account. Any Bearer token accepted single-user. Data in local SQLite file.
5. Later (Phase 4+): flagship FR natural-language date recognition (`"lundi 10h réunion Paris"` works as well as `"Monday 10am meeting in Paris"`) + full complete-app backlog.

## 2. V1 scope = core task flow ONLY — Complete app = ALL Todoist features REQUIRED post-V1 (do not forget)

V1 (MVP) is intentionally narrow: core task flow only.
Post-V1 we MUST build the complete app: full Todoist parity, no exceptions, including Teams and everything deferred from V1.

V1 IN:
- Inbox / Today / Upcoming, projects / sections / labels, p1-p4, due dates/times, quick-add `# @ / p1-p4` + EN dates, complete / reopen / edit / delete / search + Todoist API v1 subset + SQLite.

COMPLETE APP BACKLOG (REQUIRED post-V1, tracked here so we don't forget — every item must ship):
- Subtasks / parent-child nesting, descriptions (markdown), recurrence rules (daily/weekly/monthly + natural language), duration + deadline, reminders (`!` syntax + custom), assignees (`+` syntax)
- Comments on tasks/projects, file attachments / uploads
- Custom filters (`today | overdue`, etc), labels management UI, workspace filters, view options
- Board + Calendar views, completed-history, activity logs, karma / productivity stats
- Teams / workspaces / folders, shared projects, roles/permissions, collaborators + invites, workspace users
- Full Sync API coverage (all resource_types: notes, reminders, locations, collaborators, user_settings, stats, view_options, etc), day orders, `temp_id_mapping`
- OAuth + personal tokens, multi-user, backups/export, webhooks, emails, notifications, mobile + desktop URL schemes
- Self-hosted Docker multi-user mode (same codebase, add auth + Postgres option later)
- FR NLP flagship: full French + English date/time parsing (`lundi 10h réunion Paris` == `Monday 10am meeting Paris`), with chip preview in Quick Add
- Bilingual FR/EN UI toggle (V1 = EN to match Todoist EN web; screenshots FR used only for layout reference)
- Own Omarchy plugin (Phase 5) + maintained patched forks of omatasks + omarchy-todoist with configurable base URL

## 3. Architecture (Approach A — approved)

Single Python process `python -m opendoist` on `http://localhost:8000`:
- `FastAPI` serves both `/` (web UI) and `/api/v1/*` (compat API). No build step, no CORS issues same-origin.
- `SQLite` via stdlib `sqlite3` (V1) with single file `~/.local/share/opendoist/opendoist.db` + fallback `./data.db`. Schema migratable to Postgres later.
- Frontend: server-rendered HTML + vanilla JS + single CSS matching Todoist tokens (red `#E44332`, sidebar `#FCFAF8`, font -apple-system stack). No npm.
- Quick-add parser in Python: regex tokens `#Project`, `@label`, `/section`, `p1-p4`, `+assignee`, `!reminder`, `{deadline}` + date extraction EN in V1, FR in Phase 4 (using `dateparser` + custom rules).
- Patched-fork strategy: upstream plugins hardcode `https://api.todoist.com/api/v1/`. We keep tiny forks where base URL is env/configurable, defaulting to `http://localhost:8000/api/v1/`. No hosts/TLS hacks.

Alternatives rejected:
- B React+Vite split: prettier SPA but needs build, heavier on Omarchy, slower MVP.
- C Go binary: portable but weaker FR NLP libs + slower pixel iteration.

## 4. Components

- `app/main.py` — FastAPI app, routes for UI + API, auth dep (accept any Bearer, fixed dev token `local-dev-token` also works with empty).
- `app/db.py` — SQLite init + migrations, tables: projects, sections, labels, tasks, task_labels, filters, sync_state.
- `app/models.py` — Pydantic shapes mirroring Todoist v1 task/project/label/section JSON (ids as snowflake-ish strings, `content`, `description`, `project_id`, `section_id`, `parent_id`, `priority 1-4` where p1=4 urgent, `due {date,time,timezone,recurrence}`, `deadline`, `duration`, `labels[]`, `order`, `completed`, `created_at`).
- `app/parser.py` — `parse_quick_add(text)` -> {content, project, labels, priority, due, section, ...}. V1 EN dates (`today`, `tomorrow`, `next Monday`, `tomorrow at 5pm`, `YYYY-MM-DD`); preserves unknown text for Todoist-style passthrough.
- `app/api_v1.py` — compat endpoints (subset, see §5).
- `app/sync.py` — `POST /api/v1/sync` form-encoded handler (`sync_token`, `resource_types`), returns `{projects, items, labels, sections, filters, sync_token, full_sync}`.
- `app/web/` — `index.html`, `styles.css`, `app.js`: sidebar, Today/Inbox/Upcoming views, quick-add modal, task rows with priority circles, complete checkbox, edit/delete, search, display grouping/sorting (Smart: date/time → priority → manual).
- `tests/` — `test_api_compat.py`, `test_parser.py`, `test_plugin_compat.py` (mimics both plugins' call sequences).

## 5. API compatibility (V1 subset — enough for both plugins)

- `GET /api/v1/tasks` — list active (supports `project_id`, `label`, `limit`).
- `GET /api/v1/tasks/filter?query=` — support `today`, `overdue`, `today | overdue`, `inbox`, `#Project`, `@label`, `p1..p4` minimal parser. omatasks + omarchy-todoist Today/Inbox/All map here.
- `POST /api/v1/tasks/quick` `{text}` — quick-add with parser, returns task. Bare `Buy milk` defaults due today (matching omarchy-todoist behavior).
- `GET /api/v1/tasks/{id}`, `POST /api/v1/tasks/{id}` (partial update, only changed fields), `DELETE /api/v1/tasks/{id}`
- `POST /api/v1/tasks/{id}/close` (complete; recurring stub advances one day in full vision), `POST /api/v1/tasks/{id}/reopen`, `POST /api/v1/tasks/{id}/move` (project/section)
- Projects: `GET/POST /api/v1/projects`, `GET/POST/DELETE /api/v1/projects/{id}`, archive/unarchive
- Sections: `GET/POST /api/v1/sections`, `GET/POST/DELETE /api/v1/sections/{id}`
- Labels: `GET/POST /api/v1/labels`, `GET/POST/DELETE /api/v1/labels/{id}`
- `POST /api/v1/sync` — `application/x-www-form-urlencoded`, `sync_token='*' | incremental`, `resource_types='[\"all\"]'` or subset. Returns Todoist-shaped sync payload.
- Auth: `Authorization: Bearer <anything>` accepted. `401` only if missing (Todoist-style `{error_tag, error_code 477}`).
- IDs: server-generated numeric-string IDs (Todoist v1 style). Reject `tmp-` prefix with validation error like upstream.

Out of V1: comments, reminders CRUD, collaborators, workspaces, backups, activity, webhooks, uploads, OAuth.

## 6. Data flow

Quick-add `Buy milk tomorrow #Shopping p1` -> `parser` extracts `{content: Buy milk, due: tomorrow, project: Shopping, priority: 4}` -> insert SQLite -> return same JSON to UI + API callers. `GET /tasks/filter?query=today` reads same table, formats Todoist shape. Sync returns full snapshot on `*`, then incremental via `updated_at > last_token`. UI and plugins see identical state.

## 7. Error handling

- API errors use Todoist JSON `{error, error_code, error_tag, http_code}` + proper HTTP codes. `401` missing token, `404` unknown id, `400` validation (`tmp-` ids, bad dates).
- UI toasts on failure, failed quick-add preserves draft text for retry (like omatasks). Bulk actions (future) offer retry-remaining.
- DB writes transactional; reorder uses fractional order keys.

## 8. Testing

- `pytest tests/test_parser.py` — EN dates, `# @ p1` tokens, escaped names, precedence.
- `pytest tests/test_api_compat.py` — CRUD, filter `today|overdue`, quick-add defaults, close/reopen, sync `*` + incremental.
- `pytest tests/test_plugin_compat.py` — replays both plugins' sequences with controlled token, asserts shapes.
- Manual: screenshot compare web UI vs Todoist web (sidebar, Today groups, priority colors p1 red p2 yellow p3 blue).
- Gate before Phase 3: all green + both patched forks point to localhost and list/complete/add.

## 9. Phases

- Phase 0: scaffold + DB + design doc (this file) + CI.
- Phase 1: API compat + EN parser + tests.
- Phase 2: pixel web UI (Today/Inbox/Upcoming, projects/labels, quick-add modal).
- Phase 3: patched-fork validation vs live localhost.
- Phase 4: FR NLP flagship (`lundi 10h`, `demain`, `la semaine prochaine`) + chip preview + start complete-app backlog.
- Phase 5+: complete app — MUST include teams/workspaces, subtasks, recurrence, board/calendar, comments, reminders, filters, activity, Docker self-hosted. No feature left behind.

## 10. Self-review (placeholder scan)

No TBDs. Scope split explicit (V1 vs full vision). No contradictions (EN V1, FR Phase 4; monolith now, Docker later same codebase). No ambiguity on auth (any token) or default due (bare task -> today).
