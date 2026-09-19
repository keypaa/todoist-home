# OpenDoist — Design Spec (2026-09-19, rev2 after reviewer)

> Free, local-first Todoist clone. EN-first UI. Single FastAPI monolith + SQLite.
> Repo: https://github.com/keypaa/todoist-home
> Status: brainstorming approved + subagent review incorporated. V1 = core flow tiered. Complete app REQUIRED post-V1 (teams included).
> Disclaimer (required in README + UI footer): "Not created by, affiliated with, or supported by Todoist."

## 1. Goal / Success criteria

Build a free Todoist (web version) clone named **OpenDoist** that:
1. Looks/feels like Todoist web (sidebar: Add task, Search, Inbox, Today, Upcoming, Filters & Labels, Projects; main Today view Overdue/Today split, Upcoming grouped by date, EN).
2. Exposes a **Todoist API v1-compatible** local API so Omarchy plugins work without a Todoist account. Primary target:
   - https://github.com/crmne/omatasks (form-encoded incremental Sync with `commands[]`, JSON Quick Add, task close, multi-select bulk, drag reorder via `order_key` + `day_orders`, reminders, deadlines, sections, assignees, duplication) — we maintain ONE patched fork with configurable base URL.
   - https://github.com/Aryan-Techie/omarchy-todoist is API-compatible (`GET /tasks/filter`, `GET /tasks`, `POST /tasks/quick`, `POST /tasks/{id}`, `POST /tasks/{id}/close`, `DELETE /tasks/{id}`) so it works against our API, but we will NOT fork it — omatasks only.
3. V1 must pass: web UI manual test + `pytest` API compat + plugin-compat script mimicking omatasks sequence (Sync read+write, quick-add, close, reorder, bulk).
4. No paywall, no account. Any Bearer token accepted single-user, bind `127.0.0.1:8000` only. Data in local SQLite file with WAL.
5. Later (Phase 4+): flagship FR NLP (`"lundi 10h réunion Paris"` == `"Monday 10am meeting Paris"`) + complete-app backlog.

## 2. V1 scope = core task flow ONLY — Complete app = ALL Todoist features REQUIRED post-V1

V1 (MVP) is intentionally narrow: core task flow only.
Post-V1 we MUST build the complete app: full Todoist parity, no exceptions, including Teams and everything deferred from V1.

V1 IN — tiered (V1 time window only, build in order):

- Tier V1-T0 — Foundation (first): repo scaffold, FastAPI monolith bound to 127.0.0.1:8000, SQLite schema with `user_id` column (single row now, multi-user later) + WAL + `busy_timeout`, tables: users, projects, sections, labels, tasks, task_labels, filters, reminders, day_orders, sync_state. Auth: `Authorization: Bearer <anything>` accepted; missing header -> 401 Todoist shape. CI + pytest skeleton.
- Tier V1-T1 — Daily-usable + early plugin-testable (second): task CRUD, `POST /tasks/quick` EN parser (`# @ % / p1-p4 +assignee !reminder {deadline}` + `today/tomorrow/next Monday/YYYY-MM-DD`), Today/Inbox/Upcoming web UI minimal, complete/reopen/edit/delete, bare `Buy milk` defaults due today **server-side** (both UI + API). Minimal `POST /sync` read (`sync_token='*'`, `resource_types=["user","items","projects"]`) + quick + close so `test_plugin_compat` runs early. Auto-create Inbox project; quick-add `#Project`/`/section` auto-creates if missing.
- Tier V1-T2 — Organization + full omatasks compat (third): projects/sections/labels CRUD (+ archive flags), `GET /tasks` (params `project_id,label,limit`, sorted due->priority, paginated) + `GET /tasks/filter?query=` (`today`, `overdue` time-aware `datetime<now`, `today | overdue` union, `inbox`, `#Project` incl. quoted, `@label` + `%` alias, `p1..p4` where p1=priority 4), search, priorities UI, due times + timezones, Smart sorting (date/time → priority → deadline → manual), full `POST /sync` read+write (see §5).
- Tier V1-T3 — Pixel polish + validation (last in V1): Todoist CSS tokens, Overdue/Today split, Upcoming grouped by date, project+section on row, `#Project @labels` under due, priority circles p1 red/p2 yellow/p3 blue, quick-add chips + `↑/↓ Enter Tab Esc … Ctrl+Enter`, display menu (group none/project/label, sort smart/manual), multi-select highlight, detail popup (description/dates/labels/project/section/assignee/deadline/duration/reminders + subtask progress), drag insertion line + auto-scroll + Esc-cancel, toasts + session draft preserve, bar-count rule (today+overdue mine+unassigned). Screenshot compare + omatasks-fork validation vs localhost + docs.

COMPLETE APP BACKLOG (REQUIRED post-V1, separate time window — tiered, build in order, every item must ship):
- Tier C-T1 — Task depth: subtasks/parent-child, descriptions markdown, recurrence full, duration/deadline full, reminders CRUD, assignees, comments, uploads.
- Tier C-T2 — Views & productivity: custom filters CRUD, labels UI, workspace filters, view options, Board+Calendar, completed-history, activity logs, karma/stats, `temp_id_mapping` full.
- Tier C-T3 — Collaboration & Teams (explicitly required): Teams/workspaces/folders, shared projects, roles/permissions, collaborators+invites, workspace users, full Sync resource_types (notes, reminders, locations, collaborators, user_settings, stats, view_options, etc).
- Tier C-T4 — Platform & flagship: OAuth+personal tokens, multi-user, backups/export, webhooks, emails, notifications, mobile+desktop URL schemes, Docker self-hosted (+Postgres), FR NLP flagship + chip preview, FR/EN toggle (V1=EN).
- Tier C-T5 — Omarchy: maintained patched fork of omatasks ONLY with configurable base URL (no omarchy-todoist fork).

## 3. Architecture (Approach A — approved)

Single Python process `python -m opendoist` on `http://127.0.0.1:8000`:
- FastAPI serves `/` (UI) + `/api/v1/*` (compat). No build, same-origin.
- SQLite stdlib `sqlite3`, WAL, single-writer, transactional batches. File `~/.local/share/opendoist/opendoist.db` fallback `./data.db`. `user_id` default `1` for future Postgres migration.
- Frontend vanilla HTML/JS/CSS, Todoist tokens red `#E44332`, sidebar `#FCFAF8`.
- Parser Python: regex tokens + EN dates V1, FR Phase 4 (`dateparser` + custom). Precedence: `p1-p4` > `#`/`@`/`%` > `/` > `+` > `!` > `{}` > dates; escaped `\# \@`; quoted `#"My Project"`; chip preview local EN, unknown strings passthrough via `due.string`.
- Fork: replace hardcoded `https://api.todoist.com/api/v1` with config default `http://localhost:8000/api/v1`, handle trailing slash, form-encoding, `Authorization` header. Token validation via `resource_types:["user"]` must succeed.

Alternatives rejected: B React split (build heaviness), C Go binary (weaker FR NLP + slower UI).

## 4. Components

- `app/main.py` — routes + auth dep (any Bearer; missing -> 401; no empty-bypass ambiguity).
- `app/db.py` — init/migrations incl. `day_orders(task_id, day, order)`, `order_key` fractional text, `is_deleted` tombstones, `is_archived`.
- `app/models.py` — Todoist v1 shapes: task `{id, user_id, content, description, project_id, section_id, parent_id, priority 1-4 (p1=4), due{date,datetime,timezone,string,lang,is_recurring}, deadline{date}, duration{amount,unit}, labels[], responsible_uid/assignee_id, order_key, day_order, completed, created_at, updated_at}`, project/section `{is_archived,is_deleted}`, label, filter, reminder, user `{id}`.
- `app/parser.py` — `parse_quick_add(text)` + `parse_filter(query)` + `parse_reminder(!)` + `parse_deadline({})`.
- `app/api_v1.py` — REST subset (§5).
- `app/sync.py` — form-encoded read+write with `commands[]`, `uuid` idempotency, batch 100 chaining, `sync_status`, `temp_id_mapping` (Sync UUIDs) distinct from REST `tmp-` rejection.
- `app/web/` — `index.html/styles.css/app.js` per T3 fidelity list.
- `tests/` — `test_parser.py`, `test_api_compat.py`, `test_sync_write.py`, `test_plugin_compat.py` (omatasks only).

## 5. API compatibility (V1 — must satisfy omatasks)

REST:
- `GET /api/v1/tasks` + `GET /api/v1/tasks/filter?query=` as §2 T2. Sort due->priority->deadline->manual. `overdue` time-aware. `inbox` = inbox-project.
- `POST /api/v1/tasks/quick {text, auto_reminder}` — accept+ignore `auto_reminder`, honor `X-Request-Id` idempotency, return task with `due.string/lang` fallback, bare text -> due today server-side.
- `GET /api/v1/tasks/{id}`, `POST /api/v1/tasks/{id}` partial (only changed fields; title-only edit must not reinterpret `due.string` or reset recurrence/timezone), `DELETE`, `POST .../close` (hide task+children from active; V1 no fake recurrence advance — server reschedule comes with C-T1), `POST .../reopen`, `POST .../move` (project/section) + Sync `item_move` both supported.
- Projects/sections/labels CRUD + archive/unarchive (+ `is_archived` for sections too). Filters read; full CRUD in C-T2.
- IDs numeric-string; REST rejects `tmp-...` with 400 validation; Sync `temp_id` UUID accepted + returned in `temp_id_mapping` — separate concepts.

SYNC `POST /api/v1/sync` (`application/x-www-form-urlencoded`):
- Read: `sync_token='*'|incremental`, `resource_types` subset. `refresh()` uses `["items","projects","sections","labels","user","collaborators","reminders","completed_info"]`; `connectToken` uses `["user"]`. Response must include `user{id}`, `projects`, `items`, `sections`, `labels`, `collaborators[]`, `reminders[]`, `completed_info[]`, `day_orders{id:n}`, `filters`, `temp_id_mapping{}`, `sync_status{}` (on writes), `sync_token`, `full_sync`. Apply `is_deleted`/`is_archived` filtering + tombstones (not just `updated_at`).
- Write `commands[]`: `item_add` (with `temp_id`, duplicate-with-children + `parent_id` remap, without comments/reminders), `item_update` (partial incl. `order_key`, description/due/deadline/duration/labels/assignee/section/project + `due.string` passthrough + `timezone` preserve), `item_move`, `item_close`, `item_delete`, `item_update_day_orders {ids_to_orders}`, `reminder_add`. Return `sync_status{uuid:"ok"|{error}}`, new `sync_token`, `temp_id_mapping`. `uuid` retry = no double-execute. Max 100/batch, chain + remap across batches. Partial failure -> per-uuid error for "Retry remaining".
- Validation: `deadlineDate` only `Today|Tomorrow|Next week|YYYY-MM-DD` else 400; `reminderArgs` `30mb/2h`/text mapping to `minute_offset` or `due:{string}`; only-changed-fields rule.

Auth/errors: missing token -> 401 `{error_tag:UNAUTHORIZED,error_code:477}`; unknown id 404; validation 400 non-retryable; 429 with `Retry-After`. REST error shape + per-command `sync_status` errors both required.

Out of V1: comments CRUD, workspaces/collaborators writes, backups, activity, webhooks, uploads, OAuth.

## 6. Data flow

`quick-add text -> parser (+due.string fallback) -> SQLite txn -> same JSON to UI + REST + Sync`. `filter?query=today` + Sync views read same tables. Sync `*` full snapshot, then incremental via token + tombstones. `day_orders` for Today/Upcoming reorder (scoped per day/group), `order_key` fractional for Inbox (scoped section+parent, hidden siblings preserved, rollback on fail, force Manual sort per view). UI + omatasks see identical state.

## 7. Timezone + error handling

- Store `date` + optional `datetime` + `timezone`. Floating vs fixed preserved. Today/overdue grouping compares in task tz (fallback server local). Edit preserves `timezone` unless new time given. Tests cover tz boundaries.
- REST errors Todoist JSON + HTTP codes; Sync per-uuid errors. UI toasts, failed quick-add preserves draft, bulk offers retry-remaining. 429 honors `Retry-After`. DB txn + WAL.

## 8. Testing

- `test_parser`: EN dates, `# @ % / p1 + ! {}` precedence, escaped, quoted, chip vs passthrough, `p1→4`.
- `test_api_compat`: CRUD, filter union, quick default-today, close/reopen (children hidden), move, `X-Request-Id`, `tmp-` reject, deadline/reminder validation, title-only edit preserves recurrence/tz.
- `test_sync_write`: `*` + incremental + deletes/archives, `user` validation, commands all types, `uuid` retry, batch-100 chaining + `temp_id_mapping` parent remap, partial-failure retry, `day_orders` vs `order_key` reorder + rollback, duplicate without comments/reminders.
- `test_plugin_compat`: replay omatasks connect→refresh→quick→edit→bulk→reorder→close→resync with fixed token, assert shapes incl. `sync_status/temp_id_mapping/day_orders`.
- Manual screenshot compare (Overdue/Today, Upcoming by date, priority colors, chips, display menu, detail popup, drag line).
- Gate = end of Phase 2 (V1-T3): all green + omatasks fork lists/completes/adds/reorders vs localhost.

## 9. Phases

- Phase 0: scaffold + DB + spec + CI.
- Phase 1 (V1-T0+T1): minimal API + EN parser + minimal sync read + tests early.
- Phase 2 (V1-T2+T3): full omatasks compat + pixel UI + polish. Gate here.
- Phase 3: omatasks-fork validation live (no omarchy-todoist fork).
- Phase 4: FR NLP + chip + C-T1 start.
- Phase 5+: C-T1→C-T5 in order, teams included, no feature left.

## 10. Self-review (rev2)

Fixed rev1 gaps: sync write path, read shape (`user/collaborators/reminders/completed_info/day_orders`), reorder dual mechanism, V1 passthrough of description/due-string/deadline/duration/assignee/reminder, quick `auto_reminder`+`X-Request-Id`+today-default server-side, close semantics (no fake +1 day), duplication, tier ordering (auto-create + early sync), filter pinning, timezones, parser precedence, Smart+deadline, UI fidelity list, expanded tests, trademark disclaimer, 127.0.0.1-only, WAL, `user_id` for migration, QML base URL, `tmp-` vs `temp_id` split, move both paths, phase gate = end Phase 2. No TBDs.
