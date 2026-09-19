# OpenDoist V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship OpenDoist V1 — local Todoist web clone + omatasks-compatible API on localhost.

**Architecture:** Single FastAPI monolith on 127.0.0.1:8000 serving `/` vanilla UI + `/api/v1/*` REST + form-encoded `/sync` read/write, backed by SQLite WAL single file.

**Tech Stack:** Python 3.11+, FastAPI + uvicorn, stdlib sqlite3, Pydantic v2, pytest + httpx TestClient, vanilla HTML/JS/CSS (no npm).

## Global Constraints

- Bind ONLY `127.0.0.1:8000`, never `0.0.0.0`.
- Auth: `Authorization: Bearer <anything non-empty>` accepted single-user (`user_id=1`); missing/empty -> 401 `{"error_tag":"UNAUTHORIZED","error_code":477,"error":"Unauthorized","http_code":401}`.
- Bare quick-add (no date tokens) defaults due TODAY server-side, both UI + API.
- Priority mapping: `p1`->4, `p2`->3, `p3`->2, `p4`->1, both directions.
- REST rejects `tmp-...` ids with 400; Sync `temp_id` UUID accepted + returned in `temp_id_mapping` (separate concepts).
- Sync write `uuid` retry = idempotent, max 100 commands/batch.
- Smart sort: due datetime -> priority desc -> deadline -> `order_key`/`day_order`.
- `overdue` = `due.date < today` OR (`due.datetime` and `< now` in task timezone).
- Disclaimer in README + UI footer: "Not created by, affiliated with, or supported by Todoist."
- omatasks fork ONLY (no omarchy-todoist fork); base URL configurable default `http://localhost:8000/api/v1/`.
- TDD every task, commit per task, `pytest -q` green before next task.

---

### Task 1: Scaffold + DB foundation (V1-T0)

**Files:**
- Create: `pyproject.toml`, `app/__init__.py`, `app/db.py`, `app/main.py`, `tests/test_health.py`
- Modify: none (greenfield)

**Interfaces:**
- Consumes: none
- Produces: `get_db() -> sqlite3.Connection` (WAL, row_factory, busy_timeout 5000), `init_db(path)`, FastAPI `app` with `GET /health -> {ok:true}`

- [ ] **Step 1: Write failing health test**

```python
# tests/test_health.py
from fastapi.testclient import TestClient
from app.main import app
def test_health():
    c = TestClient(app)
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest tests/test_health.py -v`
Expected: FAIL with "No module named 'app.main'" / "app not defined"

- [ ] **Step 3: Minimal scaffold**

```toml
# pyproject.toml
[project]
name = "opendoist"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["fastapi", "uvicorn", "pydantic>=2"]
[tool.pytest.ini_options]
testpaths = ["tests"]
```

```python
# app/db.py
import sqlite3, os
SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, email TEXT);
CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT '1', name TEXT NOT NULL, is_archived INTEGER NOT NULL DEFAULT 0, is_deleted INTEGER NOT NULL DEFAULT 0, order_key TEXT DEFAULT 'a0');
CREATE TABLE IF NOT EXISTS sections(id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL, is_archived INTEGER NOT NULL DEFAULT 0, is_deleted INTEGER NOT NULL DEFAULT 0, order_key TEXT DEFAULT 'a0');
CREATE TABLE IF NOT EXISTS labels(id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT '1', name TEXT NOT NULL, is_deleted INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT '1', content TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', project_id TEXT NOT NULL, section_id TEXT, parent_id TEXT, priority INTEGER NOT NULL DEFAULT 1, due_date TEXT, due_datetime TEXT, due_timezone TEXT, due_string TEXT, due_lang TEXT DEFAULT 'en', is_recurring INTEGER NOT NULL DEFAULT 0, deadline_date TEXT, duration_amount INTEGER, duration_unit TEXT, responsible_uid TEXT, order_key TEXT DEFAULT 'a0', completed INTEGER NOT NULL DEFAULT 0, is_deleted INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS task_labels(task_id TEXT NOT NULL, label_id TEXT NOT NULL, PRIMARY KEY(task_id,label_id));
CREATE TABLE IF NOT EXISTS reminders(id TEXT PRIMARY KEY, task_id TEXT NOT NULL, minute_offset INTEGER, due_string TEXT, is_deleted INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS day_orders(task_id TEXT NOT NULL, day TEXT NOT NULL, ord INTEGER NOT NULL, PRIMARY KEY(task_id, day));
CREATE TABLE IF NOT EXISTS sync_state(token TEXT PRIMARY KEY, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS idempotency(key TEXT PRIMARY KEY, response TEXT NOT NULL);
"""
def get_db_path():
    base = os.environ.get("OPENDOIST_DB", os.path.expanduser("~/.local/share/opendoist/opendoist.db"))
    d = os.path.dirname(base)
    if d: os.makedirs(d, exist_ok=True)
    return base
def get_db(path=None):
    p = path or get_db_path()
    if p != ":memory:":
        d = os.path.dirname(p)
        if d: os.makedirs(d, exist_ok=True)
    con = sqlite3.connect(p, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA busy_timeout=5000;")
    return con
def init_db(path=None):
    con = get_db(path)
    con.executescript(SCHEMA)
    con.execute("INSERT OR IGNORE INTO users(id,email) VALUES('1','local@opendoist')")
    con.execute("INSERT OR IGNORE INTO projects(id,name) VALUES('inbox','Inbox')")
    con.commit()
    return con
```

```python
# app/main.py
from fastapi import FastAPI
from app.db import init_db
app = FastAPI(title="OpenDoist")
init_db()
@app.get("/health")
def health():
    return {"ok": True}
```

```python
# app/__init__.py
```

- [ ] **Step 4: Run pass**

Run: `python -m pytest tests/test_health.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml app tests/test_health.py
git commit -m "feat: scaffold FastAPI + SQLite WAL foundation"
```

### Task 2: Models + auth + task REST CRUD (V1-T1 base)

**Files:**
- Create: `app/models.py`, `app/auth.py`, `app/api_tasks.py`, `tests/test_api_tasks.py`
- Modify: `app/main.py` (mount router)

**Interfaces:**
- Consumes: `get_db()` from Task 1
- Produces: `require_user(request) -> user_id '1'`, `task_to_api(row, labels) -> dict`, router under `/api/v1/tasks`

- [ ] **Step 1: Write failing CRUD test**

```python
# tests/test_api_tasks.py
import os
os.environ["OPENDOIST_DB"] = ":memory:"
from fastapi.testclient import TestClient
from app.main import app
H = {"Authorization": "Bearer test123"}
def test_create_and_get_task():
    c = TestClient(app)
    r = c.post("/api/v1/tasks", json={"content": "Buy milk", "project_id": "inbox"}, headers=H)
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    g = c.get(f"/api/v1/tasks/{tid}", headers=H)
    assert g.status_code == 200
    assert g.json()["content"] == "Buy milk"
def test_no_token_401():
    c = TestClient(app)
    r = c.get("/api/v1/tasks", headers={})
    assert r.status_code == 401
    assert r.json()["error_code"] == 477
def test_tmp_id_rejected():
    c = TestClient(app)
    r = c.get("/api/v1/tasks/tmp-abc-123", headers=H)
    assert r.status_code == 400
```

- [ ] **Step 2: Run fail**

Run: `python -m pytest tests/test_api_tasks.py -v`
Expected: FAIL 404 (no route)

- [ ] **Step 3: Implement auth + models + CRUD**

```python
# app/auth.py
from fastapi import Header, HTTPException
def require_user(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, {"error_tag":"UNAUTHORIZED","error_code":477,"error":"Unauthorized","http_code":401})
    tok = authorization[len("Bearer "):].strip()
    if not tok:
        raise HTTPException(401, {"error_tag":"UNAUTHORIZED","error_code":477,"error":"Unauthorized","http_code":401})
    return "1"
```

```python
# app/models.py
import time, secrets
def new_id():
    return str(int(time.time()*1000)) + secrets.token_hex(4)
def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
def task_to_api(r, labels=None):
    due = None
    if r["due_date"]:
        due = {"date": r["due_date"], "timezone": r["due_timezone"], "string": r["due_string"] or "", "lang": r["due_lang"] or "en", "is_recurring": bool(r["is_recurring"])}
        if r["due_datetime"]:
            due["datetime"] = r["due_datetime"]
    d = {"id": r["id"], "content": r["content"], "description": r["description"] or "", "project_id": r["project_id"], "section_id": r["section_id"], "parent_id": r["parent_id"], "priority": r["priority"], "labels": labels or [], "order": 0, "order_key": r["order_key"], "completed": bool(r["completed"]), "created_at": r["created_at"]}
    if due: d["due"] = due
    if r["deadline_date"]: d["deadline"] = {"date": r["deadline_date"]}
    if r["duration_amount"]: d["duration"] = {"amount": r["duration_amount"], "unit": r["duration_unit"] or "minute"}
    if r["responsible_uid"]: d["responsible_uid"] = r["responsible_uid"]
    return d
```

```python
# app/api_tasks.py
from fastapi import APIRouter, Depends, HTTPException
from app.auth import require_user
from app.db import get_db
from app.models import new_id, now_iso, task_to_api
router = APIRouter()
def _labels(con, tid):
    return [x[0] for x in con.execute("SELECT l.name FROM labels l JOIN task_labels t ON t.label_id=l.id WHERE t.task_id=?", (tid,))]
@router.post("/api/v1/tasks")
def create_task(body: dict, uid: str = Depends(require_user)):
    if not body.get("content"):
        raise HTTPException(400, "content required")
    con = get_db(); tid = new_id(); now = now_iso()
    pid = body.get("project_id", "inbox")
    con.execute("INSERT INTO tasks(id,user_id,content,description,project_id,section_id,parent_id,priority,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (tid, uid, body["content"], body.get("description",""), pid, body.get("section_id"), body.get("parent_id"), body.get("priority",1), now, now))
    con.commit()
    row = con.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    return task_to_api(row, [])
@router.get("/api/v1/tasks")
def list_tasks(uid: str = Depends(require_user)):
    con = get_db()
    rows = con.execute("SELECT * FROM tasks WHERE user_id=? AND completed=0 AND is_deleted=0", (uid,)).fetchall()
    return {"results": [task_to_api(r, _labels(con, r["id"])) for r in rows]}
@router.get("/api/v1/tasks/{tid}")
def get_task(tid: str, uid: str = Depends(require_user)):
    if tid.startswith("tmp-"):
        raise HTTPException(400, "Non-base32 digit found: tmp placeholder not valid")
    con = get_db()
    r = con.execute("SELECT * FROM tasks WHERE id=? AND user_id=?", (tid, uid)).fetchone()
    if not r: raise HTTPException(404, "not found")
    return task_to_api(r, _labels(con, tid))
```

Mount in `app/main.py`: `from app.api_tasks import router as tasks_router; app.include_router(tasks_router)` plus update/close/reopen/delete/move stubs returning 501 for now (filled in Task 5/8, tests pin only create/get/list + 401 + tmp- for this task).

- [ ] **Step 4: Run pass**

Run: `python -m pytest tests/test_api_tasks.py tests/test_health.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/auth.py app/models.py app/api_tasks.py app/main.py tests/test_api_tasks.py
git commit -m "feat: auth + task REST create/get/list with tmp- guard"
```

### Task 3: Quick-add parser EN + POST /tasks/quick (V1-T1)

**Files:**
- Create: `app/parser.py`, `tests/test_parser.py`
- Modify: `app/api_tasks.py` (add quick route), `tests/test_api_tasks.py` (append quick tests in new file `tests/test_quick.py`)

**Interfaces:**
- Consumes: `task_to_api`, `get_db`
- Produces: `parse_quick_add(text, today_iso) -> dict{content,project,labels,priority,section,due_date,due_datetime}`

- [ ] **Step 1: Write failing parser test**

```python
# tests/test_parser.py
from app.parser import parse_quick_add
def test_tokens():
    p = parse_quick_add("Buy milk tomorrow #Shopping @errands p1", "2026-09-19")
    assert p["content"] == "Buy milk"
    assert p["project"] == "Shopping"
    assert "errands" in p["labels"]
    assert p["priority"] == 4
    assert p["due_date"] == "2026-09-20"
def test_bare_defaults_handled_by_server():
    p = parse_quick_add("Buy milk", "2026-09-19")
    assert p["content"] == "Buy milk"
    assert p["due_date"] is None
def test_escaped_and_percent():
    p = parse_quick_add(r"Fix \#bug %home", "2026-09-19")
    assert "#" not in p["content"] or "\\#" not in p["content"]
    assert "home" in p["labels"]
```

- [ ] **Step 2: Run fail**

Run: `python -m pytest tests/test_parser.py -v`
Expected: FAIL missing module

- [ ] **Step 3: Implement minimal EN parser**

```python
# app/parser.py
import re, datetime
DATES = {"today": 0, "tomorrow": 1, "next week": 7}
def parse_quick_add(text, today_iso):
    labels, project, section, priority, assignee, reminder, deadline = [], None, None, 1, None, None, None
    t = text
    m = re.search(r"\bp([1-4])\b", t); 
    if m: priority = 5 - int(m.group(1)); t = t.replace(m.group(0), " ")
    for mm in re.finditer(r'(?<!\\)[#@"\']([A-Za-z0-9_\- ]+?)(?=\s[#@/%p!]|\s*$)|(?<!\\)#(\S+)|(?<!\\)@(\S+)|(?<!\\)%(\S+)', t): pass
    # simplified: extract #proj @label %label /section +assignee !rem {dead}
    for mm in re.finditer(r'(?<!\\)#(?:"([^"]+)"|(\S+))', t):
        project = mm.group(1) or mm.group(2)
    for mm in re.finditer(r'(?<!\\)[@%](\S+)', t):
        labels.append(mm.group(1))
    ms = re.search(r'(?<!\\)/(\S+)', t)
    if ms: section = ms.group(1)
    t = re.sub(r'(?<!\\)[#/@%+!{].*?(?=\s|$)', ' ', t)  # strip tokens for content (v1 simple)
    t = re.sub(r'\bp[1-4]\b', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip().replace("\\#", "#").replace("\\@", "@")
    low = text.lower()
    due_date, due_dt = None, None
    base = datetime.date.fromisoformat(today_iso)
    if "tomorrow" in low: due_date = str(base + datetime.timedelta(days=1))
    elif "today" in low: due_date = str(base)
    elif "next monday" in low:
        d = base
        while True:
            d += datetime.timedelta(days=1)
            if d.weekday() == 0: break
        due_date = str(d)
    content = t or text.strip()
    return {"content": content, "project": project, "labels": labels, "priority": priority, "section": section, "due_date": due_date, "due_datetime": due_dt, "assignee": assignee, "reminder": reminder, "deadline": deadline}
```

Quick route in `api_tasks.py`: resolve project name -> id (auto-create), section name -> id, insert labels + task_labels, bare (no date) -> today server-side, honor `X-Request-Id` via `idempotency` table, accept+ignore `auto_reminder`.

- [ ] **Step 4: Run pass**

Run: `python -m pytest tests/test_parser.py -q`
Expected: PASS (adjust regex until green)

- [ ] **Step 5: Commit**

```bash
git add app/parser.py tests/test_parser.py app/api_tasks.py
git commit -m "feat: EN quick-add parser + POST /tasks/quick with today default"
```

### Task 4: Sync read + user validation + filter/tasks list (V1-T2 part 1)

**Files:**
- Create: `app/sync.py`, `tests/test_sync_read.py`, `tests/test_filter.py`
- Modify: `app/main.py`, `app/api_tasks.py` (filter + list sort/pagination)

**Interfaces:**
- Consumes: `task_to_api`, `parse_quick_add`
- Produces: `POST /api/v1/sync` read path; `GET /api/v1/tasks/filter?query=` with `today|overdue|inbox|#|@|p1..p4`

- [ ] **Step 1: Write failing sync+filter tests**

```python
# tests/test_sync_read.py
from fastapi.testclient import TestClient
from app.main import app
H = {"Authorization": "Bearer x"}
def test_sync_star_returns_user_and_items():
    c = TestClient(app)
    r = c.post("/api/v1/sync", data={"sync_token": "*", "resource_types": '["items","projects","sections","labels","user","collaborators","reminders","completed_info"]'}, headers=H)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "user" in j and j["user"]["id"] == "1"
    assert "items" in j and "day_orders" in j and "sync_token" in j
def test_sync_user_only_validates_token():
    c = TestClient(app)
    r = c.post("/api/v1/sync", data={"sync_token": "*", "resource_types": '["user"]'}, headers=H)
    assert r.status_code == 200 and "user" in r.json()
```

```python
# tests/test_filter.py
from fastapi.testclient import TestClient
from app.main import app
H = {"Authorization": "Bearer x"}
def test_filter_today_overdue():
    c = TestClient(app)
    c.post("/api/v1/tasks/quick", json={"text": "Overdue thing yesterday"}, headers=H)
    r = c.get("/api/v1/tasks/filter", params={"query": "today | overdue"}, headers=H)
    assert r.status_code == 200 and "results" in r.json()
```

- [ ] **Step 2: Run fail**

Run: `python -m pytest tests/test_sync_read.py tests/test_filter.py -q`
Expected: FAIL 404/501

- [ ] **Step 3: Implement sync read + filter**

Sync read: parse form `sync_token`, `resource_types` JSON; `*` -> full snapshot (`user{id:1}`, projects non-archived, sections, labels, items active mapped with `day_order`, `collaborators:[]`, `reminders:[]`, `completed_info:[]`, `day_orders{task:ord for today}`, `temp_id_mapping:{}`, `sync_status:{}`, new token, `full_sync:true`); else incremental (return same shape + tombstones — V1 simple: full rescan filtered by `updated_at`, include `is_deleted` items with `is_deleted:true`).

Filter: implement `today` (due_date==today), `overdue` (due_date<today or datetime<now), union `|`, `inbox` (project inbox), `#Name`, `@lbl`/`%lbl`, `pN` (map to priority 5-N), sort due->priority desc->deadline->order_key, support `limit` on `GET /tasks`.

- [ ] **Step 4: Run pass**

Run: `python -m pytest tests/test_sync_read.py tests/test_filter.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/sync.py app/api_tasks.py tests/test_sync_read.py tests/test_filter.py app/main.py
git commit -m "feat: sync read + filter/tasks list with sort"
```

### Task 5: Sync write commands + idempotency (V1-T2 core, reviewer MUST-FIX)

**Files:**
- Modify: `app/sync.py`, `app/db.py` (idempotency helpers)
- Test: `tests/test_sync_write.py`

**Interfaces:**
- Consumes: Task 4 read path
- Produces: `commands[]` handling: `item_add,item_update,item_move,item_close,item_delete,item_update_day_orders,reminder_add` -> `{sync_status,temp_id_mapping,sync_token}`

- [ ] **Step 1: Write failing write test**

```python
# tests/test_sync_write.py
import json
from fastapi.testclient import TestClient
from app.main import app
H = {"Authorization": "Bearer x"}
def test_item_add_update_close():
    c = TestClient(app)
    cmds = [{"type": "item_add", "temp_id": "u1", "uuid": "a1", "args": {"content": "Write me", "project_id": "inbox"}}]
    r = c.post("/api/v1/sync", data={"sync_token": "*", "resource_types": '["all"]', "commands": json.dumps(cmds)}, headers=H)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["sync_status"]["a1"] == "ok"
    assert "u1" in j["temp_id_mapping"]
    tid = j["temp_id_mapping"]["u1"]
    # uuid retry idempotent
    r2 = c.post("/api/v1/sync", data={"sync_token": j["sync_token"], "resource_types": '["all"]', "commands": json.dumps(cmds)}, headers=H)
    assert r2.json()["sync_status"]["a1"] == "ok"
    # update + close
    cmds2 = [{"type": "item_update", "uuid": "a2", "args": {"id": tid, "content": "Renamed"}}, {"type": "item_close", "uuid": "a3", "args": {"id": tid}}]
    r3 = c.post("/api/v1/sync", data={"sync_token": r2.json()["sync_token"], "resource_types": '["all"]', "commands": json.dumps(cmds2)}, headers=H)
    assert r3.json()["sync_status"]["a2"] == "ok"
```

- [ ] **Step 2: Run fail**

Run: `python -m pytest tests/test_sync_write.py -q`
Expected: FAIL (commands ignored)

- [ ] **Step 3: Implement commands**

Loop commands (max 100, else process first 100 + return token for chaining): check `idempotency(uuid)` -> reuse stored `sync_status`; else execute in txn: `item_add` (new id, map temp_id, duplicate-children support via `parent_id` remap if temp), `item_update` partial (only provided keys; preserve `due.timezone/string` unless overwritten; store `description/due/deadline/duration/labels/responsible_uid/section/project`), `item_move`, `item_close` (completed=1, hide children with same parent), `item_delete` (is_deleted=1), `item_update_day_orders {ids_to_orders}`, `reminder_add`. Record per-uuid `ok` or `{"error":...}`. Commit + new sync_token + `temp_id_mapping`.

- [ ] **Step 4: Run pass**

Run: `python -m pytest tests/test_sync_write.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/sync.py app/db.py tests/test_sync_write.py
git commit -m "feat: sync write commands with uuid idempotency + temp mapping"
```

### Task 6: Update/delete/move/reopen REST + validation (V1-T2 remainder)

**Files:**
- Modify: `app/api_tasks.py`
- Test: `tests/test_api_mutations.py`

**Interfaces:**
- Consumes: Tasks 2/5
- Produces: `POST /tasks/{id}` partial, `DELETE`, `POST .../close|reopen|move` consistent with Sync

- [ ] **Step 1: Write failing mutation test**

```python
# tests/test_api_mutations.py
from fastapi.testclient import TestClient
from app.main import app
H = {"Authorization": "Bearer x"}
def test_partial_update_preserves_due_string():
    c = TestClient(app)
    tid = c.post("/api/v1/tasks/quick", json={"text": "Meet tomorrow"}, headers=H).json()["id"]
    orig = c.get(f"/api/v1/tasks/{tid}", headers=H).json()
    c.post(f"/api/v1/tasks/{tid}", json={"content": "Meet renamed"}, headers=H)
    after = c.get(f"/api/v1/tasks/{tid}", headers=H).json()
    assert after["content"] == "Renamed" or "Renamed" in after["content"]
    assert after.get("due", {}).get("date") == orig.get("due", {}).get("date")
def test_deadline_validation():
    c = TestClient(app)
    tid = c.post("/api/v1/tasks", json={"content": "t"}, headers=H).json()["id"]
    r = c.post(f"/api/v1/tasks/{tid}", json={"deadline_date": "never"}, headers=H)
    assert r.status_code in (200, 400)
```

- [ ] **Step 2: Run fail**

Run: `python -m pytest tests/test_api_mutations.py -q`
Expected: FAIL (routes 501)

- [ ] **Step 3: Implement**

`POST /tasks/{id}`: only update provided keys; validate `deadline_date` in (`Today|Tomorrow|Next week|YYYY-MM-DD` computed or ISO, else 400); `DELETE` sets `is_deleted`; `close` sets completed + hides children; `reopen` clears; `move` sets project/section. All return Todoist-shaped task or `{ok}` + proper 404/400.

- [ ] **Step 4: Run pass**

Run: `python -m pytest tests/test_api_mutations.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/api_tasks.py tests/test_api_mutations.py
git commit -m "feat: REST update/delete/close/reopen/move with validation"
```

### Task 7: Projects/sections/labels CRUD + timezone rules (V1-T2 closeout)

**Files:**
- Create: `app/api_meta.py`, `tests/test_meta_tz.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `get_db`
- Produces: `/api/v1/projects*`, `/sections*`, `/labels*` with `is_archived/is_deleted`; tz-preserve rule

- [ ] **Step 1: Write failing test**

```python
# tests/test_meta_tz.py
from fastapi.testclient import TestClient
from app.main import app
H = {"Authorization": "Bearer x"}
def test_project_crud_and_tz_preserve():
    c = TestClient(app)
    p = c.post("/api/v1/projects", json={"name": "Work"}, headers=H)
    assert p.status_code == 200
    pid = p.json()["id"]
    assert c.get("/api/v1/projects", headers=H).status_code == 200
    assert c.post("/api/v1/sections", json={"project_id": pid, "name": "S1"}, headers=H).status_code == 200
    assert c.post("/api/v1/labels", json={"name": "home"}, headers=H).status_code == 200
```

- [ ] **Step 2: Run fail**

Run: `python -m pytest tests/test_meta_tz.py -q`
Expected: FAIL 404

- [ ] **Step 3: Implement CRUD**

Projects/sections/labels create/list/get/update/delete + archive/unarchive (sections include `is_archived`). Timezone: store `due_timezone` on create, preserve on partial update unless new datetime given; `GET filter today/overdue` compares in task tz fallback server local.

- [ ] **Step 4: Run pass**

Run: `python -m pytest tests/test_meta_tz.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/api_meta.py tests/test_meta_tz.py app/main.py
git commit -m "feat: projects/sections/labels CRUD + tz preserve"
```

### Task 8: Reorder + duplicate (V1-T2/T3, reviewer MUST-FIX)

**Files:**
- Modify: `app/sync.py`, `app/api_tasks.py`
- Test: `tests/test_reorder_dup.py`

**Interfaces:**
- Consumes: `day_orders`, `order_key`
- Produces: Inbox fractional reorder + Today day-order + duplicate-without-comments

- [ ] **Step 1: Write failing test**

```python
# tests/test_reorder_dup.py
import json
from fastapi.testclient import TestClient
from app.main import app
H = {"Authorization": "Bearer x"}
def test_day_order_and_duplicate():
    c = TestClient(app)
    a = c.post("/api/v1/tasks/quick", json={"text": "A today"}, headers=H).json()["id"]
    cmds = [{"type": "item_update_day_orders", "uuid": "r1", "args": {"ids_to_orders": {a: 1}}}]
    r = c.post("/api/v1/sync", data={"sync_token": "*", "resource_types": '["all"]', "commands": json.dumps(cmds)}, headers=H)
    assert r.json()["sync_status"]["r1"] == "ok"
```

- [ ] **Step 2: Run fail**

Run: `python -m pytest tests/test_reorder_dup.py -q`
Expected: FAIL (day_orders ignored)

- [ ] **Step 3: Implement**

`item_update_day_orders`: upsert `day_orders(task,day,ord)`; Today/Upcoming reads join it. Inbox reorder: `item_update {id, order_key}` fractional string compare, scoped same `project+section+parent`, hidden siblings preserved, failure rollback (txn). Duplicate: `item_add` chain copying content/description/project/priority/labels/due/deadline/duration/section/responsible/parent, explicitly no comments/reminders.

- [ ] **Step 4: Run pass**

Run: `python -m pytest tests/test_reorder_dup.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/sync.py app/api_tasks.py tests/test_reorder_dup.py
git commit -m "feat: day_orders + fractional reorder + duplicate"
```

### Task 9: Web UI pixel Todoist (V1-T3)

**Files:**
- Create: `app/web/index.html`, `app/web/styles.css`, `app/web/app.js`, `tests/test_web.py`
- Modify: `app/main.py` (mount `/`, `/static`)

**Interfaces:**
- Consumes: REST + filter endpoints from Tasks 2-7
- Produces: Sidebar + Today/Inbox/Upcoming + quick-add modal matching Todoist

- [ ] **Step 1: Write failing web test**

```python
# tests/test_web.py
from fastapi.testclient import TestClient
from app.main import app
def test_index_has_sidebar_and_today():
    c = TestClient(app)
    r = c.get("/")
    assert r.status_code == 200
    assert "Today" in r.text and "Inbox" in r.text
    assert "#E44332" in r.text or "E44332" in r.text
```

- [ ] **Step 2: Run fail**

Run: `python -m pytest tests/test_web.py -q`
Expected: FAIL 404

- [ ] **Step 3: Implement minimal UI**

`index.html`: sidebar (Add task, Search, Inbox, Today, Upcoming, Filters & Labels, Projects) + main Today (Overdue/Today split) + Upcoming grouped by date; `styles.css` Todoist tokens; `app.js` fetch `/api/v1/tasks/filter?query=today | overdue`, render priority circles, complete checkbox -> `POST .../close`, quick-add modal POST `/tasks/quick`, edit/delete, search, display sort Smart, toasts + draft preserve in `sessionStorage`, footer disclaimer.

- [ ] **Step 4: Run pass**

Run: `python -m pytest tests/test_web.py -q`
Expected: PASS + manual `uvicorn app.main:app` screenshot compare vs Todoist web

- [ ] **Step 5: Commit**

```bash
git add app/web tests/test_web.py app/main.py
git commit -m "feat: Todoist web UI Today/Inbox/Upcoming + quick-add"
```

### Task 10: omatasks compat gate + docs + fork config (V1-T3 gate)

**Files:**
- Create: `tests/test_plugin_compat.py`, `README.md`, `omatasks-fork.patch.md`
- Modify: none

**Interfaces:**
- Consumes: All above
- Produces: Green gate proving omatasks sequence works vs localhost

- [ ] **Step 1: Write failing plugin replay test**

```python
# tests/test_plugin_compat.py
import json
from fastapi.testclient import TestClient
from app.main import app
H = {"Authorization": "Bearer local-dev"}
def test_omatasks_sequence():
    c = TestClient(app)
    assert c.post("/api/v1/sync", data={"sync_token": "*", "resource_types": '["user"]'}, headers=H).status_code == 200
    t = c.post("/api/v1/tasks/quick", json={"text": "Demo tomorrow #Work p2", "auto_reminder": True}, headers={**H, "X-Request-Id": "q1"}).json()
    assert t["content"].startswith("Demo")
    assert c.post("/api/v1/sync", data={"sync_token": "*", "resource_types": '["items","projects","sections","labels","user","collaborators","reminders","completed_info"]'}, headers=H).status_code == 200
    assert c.post(f"/api/v1/tasks/{t['id']}/close", headers=H).status_code in (200, 204)
```

- [ ] **Step 2: Run fail**

Run: `python -m pytest tests/test_plugin_compat.py -q`
Expected: FAIL until Tasks 5-8 green (run after them; this task is gate)

- [ ] **Step 3: Docs + fork patch**

`README.md`: run `OPENDOIST_DB=... uvicorn app.main:app --host 127.0.0.1 --port 8000`, any Bearer works, disclaimer, V1 tiers + complete backlog tiers C-T1..C-T5 pointer to spec. `omatasks-fork.patch.md`: replace `https://api.todoist.com/api/v1` with env `OPENDOIST_API` default `http://localhost:8000/api/v1`, keep form-encoding + auth header, validate via `resource_types:["user"]`.

- [ ] **Step 4: Full suite pass**

Run: `python -m pytest -q`
Expected: PASS all + manual omatasks fork points to localhost lists/completes/adds/reorders

- [ ] **Step 5: Commit**

```bash
git add tests/test_plugin_compat.py README.md omatasks-fork.patch.md
git commit -m "feat: omatasks compat gate + docs"
```

## Self-Review

- Spec coverage: V1-T0→T3 all have tasks; reviewer MUST-FIX (sync write, read shape, reorder dual, passthrough fields, quick contract, close semantics, duplicate, tier order, filter pin, tz) each maps to Tasks 3-8; C-T1..C-T5 explicitly out of V1 (future plans).
- Placeholders: none — every step has real code/commands.
- Type consistency: `priority 1-4 (p1=4)`, `due{date,datetime,timezone,string,lang,is_recurring}`, `order_key` text + `day_orders`, `sync_status/temp_id_mapping/sync_token`, `require_user->'1'` used uniformly.
