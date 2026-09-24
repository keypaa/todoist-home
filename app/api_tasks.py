import datetime
import json
import os
import re
from fastapi import APIRouter, Depends, HTTPException, Request
from app.auth import require_user
from app.db import SCHEMA, get_db
from app.models import new_id, now_iso, task_to_api
from app.parser import parse_quick_add

router = APIRouter()

_mem_con = None


def _con():
    # Each sqlite3 :memory: connection owns a private empty DB, so
    # per-request get_db() calls would never see each other's tables.
    # Reuse one process-wide connection only for the :memory: test case;
    # file-backed DBs keep Task 1 per-request get_db() semantics untouched.
    global _mem_con
    if os.environ.get("OPENDOIST_DB") == ":memory:":
        if _mem_con is None:
            _mem_con = get_db()
            _mem_con.executescript(SCHEMA)
            _mem_con.execute("INSERT OR IGNORE INTO users(id,email) VALUES('1','local@opendoist')")
            _mem_con.execute("INSERT OR IGNORE INTO projects(id,user_id,name) VALUES('inbox','1','Inbox')")
            _mem_con.commit()
        return _mem_con
    return get_db()


def _labels(con, tid):
    return [x[0] for x in con.execute("SELECT l.name FROM labels l JOIN task_labels t ON t.label_id=l.id WHERE t.task_id=?", (tid,))]


def _smart_sort(items):
    def _key(t):
        due = t.get("due") or {}
        dt = due.get("datetime") or due.get("date") or "9999-12-31"
        deadline = (t.get("deadline") or {}).get("date") or "9999-12-31"
        return (dt, -(t.get("priority", 1)), deadline, t.get("order_key") or "a0", t.get("day_order") or 0)

    return sorted(items, key=_key)


def _day_order_for(con, tid, day):
    try:
        r = con.execute("SELECT ord FROM day_orders WHERE task_id=? AND day=?", (tid, day)).fetchone()
        return r["ord"] if r else 0
    except Exception:
        return 0


def _effective_due_day(task_dict, fallback):
    # Upcoming reorder: join day_orders on the task's own due day, not
    # always today. Fallback covers undated tasks (Inbox/Today default).
    due = task_dict.get("due") or {}
    d = due.get("date")
    if isinstance(d, str) and d.strip():
        try:
            datetime.date.fromisoformat(d.strip()[:10])
            return d.strip()[:10]
        except ValueError:
            pass
    dt = due.get("datetime")
    if isinstance(dt, str) and len(dt.strip()) >= 10:
        try:
            datetime.date.fromisoformat(dt.strip()[:10])
            return dt.strip()[:10]
        except ValueError:
            pass
    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip()[:10]
    return datetime.date.today().isoformat()


def _with_day_order(con, task_dict, day=None):
    try:
        eff = _effective_due_day(task_dict, day)
        task_dict["day_order"] = _day_order_for(con, task_dict.get("id"), eff)
    except Exception:
        task_dict.setdefault("day_order", 0)
    return task_dict


def _fresh_order_key(src_key, nid):
    # Inbox fractional: seed a unique key sorting just after the source so
    # the duplicate never collides. Appending keeps it between source and
    # the next sibling (e.g. "a0" -> "a0n…ab12" < "a1").
    base = src_key if isinstance(src_key, str) and src_key.strip() else "a0"
    base = base.strip()
    suffix = "".join(ch for ch in str(nid or "") if ch.isalnum())[-6:] or "x"
    return f"{base}n{suffix}"


def _strip_name(name):
    return name.rstrip(",.;:!?)").strip()


def _parse_branch(branch):
    projects, labels, pris = [], [], set()
    spans = []
    for mm in re.finditer(r'#(?:"([^"]+)"|\'([^\']+)\'|(\S+))', branch):
        name = mm.group(1) or mm.group(2) or mm.group(3)
        projects.append(_strip_name(name))
        spans.append(mm.span())
    for mm in re.finditer(r'[@%](\S+)', branch):
        labels.append(_strip_name(mm.group(1)))
        spans.append(mm.span())
    for mm in re.finditer(r'\bp([1-4])\b', branch, flags=re.IGNORECASE):
        pris.add(5 - int(mm.group(1)))
        spans.append(mm.span())
    for pat in (r'\btoday\b', r'\boverdue\b', r'\binbox\b'):
        for mm in re.finditer(pat, branch, flags=re.IGNORECASE):
            spans.append(mm.span())
    chars = list(branch)
    for s, e in sorted(spans, key=lambda x: x[0], reverse=True):
        for i in range(s, e):
            chars[i] = " "
    rest = re.sub(r"\s+", " ", "".join(chars)).strip()
    texts = [w for w in rest.split(" ") if w]
    return {
        "today": bool(re.search(r'\btoday\b', branch, flags=re.IGNORECASE)),
        "overdue": bool(re.search(r'\boverdue\b', branch, flags=re.IGNORECASE)),
        "inbox": bool(re.search(r'\binbox\b', branch, flags=re.IGNORECASE)),
        "projects": [p for p in projects if p],
        "labels": [l for l in labels if l],
        "priorities": pris,
        "texts": texts,
    }


def _parse_dt(s):
    if not s:
        return None
    try:
        t = str(s).strip()
        if t.endswith("Z"):
            t = t[:-1] + "+00:00"
        dt = datetime.datetime.fromisoformat(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _today_in_tz(tzname, fallback):
    if not tzname:
        return fallback
    try:
        from zoneinfo import ZoneInfo

        return datetime.datetime.now(ZoneInfo(str(tzname))).date().isoformat()
    except Exception:
        return fallback


def _now_in_tz(tzname, fallback_str):
    if not tzname:
        return _parse_dt(fallback_str) or datetime.datetime.now(datetime.timezone.utc)
    try:
        from zoneinfo import ZoneInfo

        return datetime.datetime.now(ZoneInfo(str(tzname)))
    except Exception:
        return _parse_dt(fallback_str) or datetime.datetime.now(datetime.timezone.utc)


def _branch_matches(task, proj_name_by_id, proj_id_by_lower, branch, today, now):
    tz = ((task.get("due") or {}).get("timezone")) or None
    today_eff = _today_in_tz(tz, today)
    now_eff = _now_in_tz(tz, now)
    if branch["today"]:
        due = task.get("due") or {}
        dd = due.get("date")
        dt = due.get("datetime") or ""
        hit = bool(dd == today_eff)
        if not hit and dt:
            pdt = _parse_dt(dt)
            if pdt is not None:
                try:
                    if tz:
                        from zoneinfo import ZoneInfo

                        pdt = pdt.astimezone(ZoneInfo(str(tz)))
                    hit = bool(pdt.date().isoformat() == today_eff)
                except Exception:
                    hit = bool(dt[:10] == today_eff)
            else:
                hit = bool(dt[:10] == today_eff)
        if not hit:
            return False
    if branch["overdue"]:
        due = task.get("due") or {}
        dd = due.get("date") or ""
        dt = due.get("datetime") or ""
        is_over = False
        if dd and dd < today_eff:
            is_over = True
        if dt:
            pdt = _parse_dt(dt)
            if pdt is not None:
                if pdt < now_eff:
                    is_over = True
            elif dt < now:
                is_over = True
        if not is_over:
            return False
    if branch["inbox"] and task.get("project_id") != "inbox":
        return False
    if branch["projects"]:
        want = set()
        for name in branch["projects"]:
            # Exact name match first, then case-insensitive.
            pid = None
            for pid_c, nm in proj_name_by_id.items():
                if nm == name:
                    pid = pid_c
                    break
            if pid is None:
                pid = proj_id_by_lower.get(name.lower())
            if pid is not None:
                want.add(pid)
        if not want or task.get("project_id") not in want:
            return False
    if branch["labels"]:
        have = {str(x).lower() for x in (task.get("labels") or [])}
        if not all(str(l).lower() in have for l in branch["labels"]):
            return False
    if branch["priorities"] and task.get("priority") not in branch["priorities"]:
        return False
    if branch["texts"]:
        content = str(task.get("content") or "").lower()
        if not all(w.lower() in content for w in branch["texts"]):
            return False
    return True


@router.post("/api/v1/tasks")
def create_task(body: dict, uid: str = Depends(require_user)):
    if not body.get("content"):
        raise HTTPException(400, "content required")
    con = _con()
    tid = new_id()
    now = now_iso()
    pid = body.get("project_id", "inbox")
    # Timezone rule: store due_timezone (+ sibling due columns) on create.
    # Partial due dict merges; flat due_* keys override. Absent -> NULL/0,
    # due_lang defaults to 'en'. Title-only updates later preserve these.
    due_dict = body.get("due") if isinstance(body.get("due"), dict) else {}
    if "due" in body and body["due"] is None:
        due_dict = None
    dd_date = dd_dt = dd_tz = dd_str = None
    dd_lang = "en"
    dd_recur = 0
    if due_dict is not None:
        if "date" in due_dict:
            dd_date = due_dict["date"]
        if "datetime" in due_dict:
            dd_dt = due_dict["datetime"]
        if "timezone" in due_dict:
            dd_tz = due_dict["timezone"]
        if "string" in due_dict:
            dd_str = due_dict["string"]
        if "lang" in due_dict:
            dd_lang = due_dict["lang"] or "en"
        if "is_recurring" in due_dict:
            dd_recur = 1 if due_dict["is_recurring"] else 0
    for flat, _col in (
        ("due_date", "date"),
        ("due_datetime", "datetime"),
        ("due_timezone", "timezone"),
        ("due_string", "string"),
        ("due_lang", "lang"),
        ("is_recurring", "recurring"),
    ):
        if flat in body:
            v = body[flat]
            if flat == "due_date":
                dd_date = v
            elif flat == "due_datetime":
                dd_dt = v
            elif flat == "due_timezone":
                dd_tz = v
            elif flat == "due_string":
                dd_str = v
            elif flat == "due_lang":
                dd_lang = v or "en"
            elif flat == "is_recurring":
                dd_recur = 1 if v else 0
    # Deadline / duration / assignee passthrough on create (parity with update/sync).
    dl_date = None
    if "deadline_date" in body:
        v = body["deadline_date"]
        dl_date = None if v is None else _parse_deadline_value(v)
    elif "deadline" in body:
        dl = body["deadline"]
        if dl is None:
            dl_date = None
        elif isinstance(dl, dict):
            d = dl.get("date")
            dl_date = None if d is None else _parse_deadline_value(d)
        elif isinstance(dl, str):
            dl_date = _parse_deadline_value(dl)
    du_amt, du_unit = None, None
    if "duration" in body:
        du = body["duration"]
        if isinstance(du, dict):
            du_amt = du.get("amount")
            if "unit" in du:
                du_unit = du.get("unit") or "minute"
        elif isinstance(du, int):
            du_amt = du
    if "duration_amount" in body:
        du_amt = body["duration_amount"]
    if "duration_unit" in body:
        du_unit = body["duration_unit"]
    resp_uid = None
    for alias in ("responsible_uid", "assignee_id", "assignee"):
        if body.get(alias) is not None:
            resp_uid = body.get(alias)
            break
    con.execute("INSERT INTO tasks(id,user_id,content,description,project_id,section_id,parent_id,priority,due_date,due_datetime,due_timezone,due_string,due_lang,is_recurring,deadline_date,duration_amount,duration_unit,responsible_uid,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (tid, uid, body["content"], body.get("description", ""), pid, body.get("section_id"), body.get("parent_id"), body.get("priority", 1), dd_date, dd_dt, dd_tz, dd_str, dd_lang, dd_recur, dl_date, du_amt, du_unit, resp_uid, now, now))
    if isinstance(body.get("labels"), list) and body["labels"]:
        _ensure_rest_labels(con, uid, tid, body["labels"])
    # Support fractional order_key on create for Inbox manual sort seeding.
    if isinstance(body.get("order_key"), str) and body["order_key"].strip():
        con.execute("UPDATE tasks SET order_key=? WHERE id=?", (body["order_key"], tid))
    con.commit()
    row = con.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    return _with_day_order(con, task_to_api(row, _labels(con, tid)))


@router.get("/api/v1/tasks")
def list_tasks(
    uid: str = Depends(require_user),
    project_id: str | None = None,
    label: str | None = None,
    limit: int | None = None,
):
    con = _con()
    rows = con.execute("SELECT * FROM tasks WHERE user_id=? AND completed=0 AND is_deleted=0", (uid,)).fetchall()
    today = datetime.date.today().isoformat()
    results = [_with_day_order(con, task_to_api(r, _labels(con, r["id"])), today) for r in rows]
    if project_id:
        results = [t for t in results if t.get("project_id") == project_id]
    if label:
        want = label.lstrip("@%").lower()
        results = [t for t in results if any(str(x).lower() == want for x in (t.get("labels") or []))]
    results = _smart_sort(results)
    if limit is not None and limit >= 0:
        results = results[:limit]
    return {"results": results}


# NOTE: registered BEFORE /tasks/{tid} so "filter" is not captured as tid.
@router.get("/api/v1/tasks/filter")
def filter_tasks(
    uid: str = Depends(require_user),
    query: str = "",
    limit: int | None = None,
):
    con = _con()
    today = datetime.date.today().isoformat()
    now = now_iso()
    rows = con.execute("SELECT * FROM tasks WHERE user_id=? AND completed=0 AND is_deleted=0", (uid,)).fetchall()
    results = [_with_day_order(con, task_to_api(r, _labels(con, r["id"])), today) for r in rows]
    prows = con.execute("SELECT id, name FROM projects WHERE user_id=?", (uid,)).fetchall()
    proj_name_by_id = {r["id"]: r["name"] for r in prows}
    proj_id_by_lower = {r["name"].lower(): r["id"] for r in prows}
    q = (query or "").strip()
    if q:
        branches = [_parse_branch(b) for b in q.split("|")]
        # A branch with zero conditions matches everything (avoids empty-OR trap).
        results = [
            t for t in results
            if any(
                (not b["today"] and not b["overdue"] and not b["inbox"] and not b["projects"] and not b["labels"] and not b["priorities"] and not b["texts"])
                or _branch_matches(t, proj_name_by_id, proj_id_by_lower, b, today, now)
                for b in branches
            )
        ]
    results = _smart_sort(results)
    if limit is not None and limit >= 0:
        results = results[:limit]
    return {"results": results}


@router.get("/api/v1/tasks/{tid}")
def get_task(tid: str, uid: str = Depends(require_user)):
    if tid.startswith("tmp-"):
        raise HTTPException(400, "Non-base32 digit found: tmp placeholder not valid")
    con = _con()
    r = con.execute("SELECT * FROM tasks WHERE id=? AND user_id=?", (tid, uid)).fetchone()
    if not r or r["is_deleted"]:
        raise HTTPException(404, "not found")
    return _with_day_order(con, task_to_api(r, _labels(con, tid)))


def _parse_deadline_value(v):
    if v is None:
        return None
    s = str(v).strip()
    low = s.lower()
    today = datetime.date.today()
    if low == "today":
        return today.isoformat()
    if low == "tomorrow":
        return (today + datetime.timedelta(days=1)).isoformat()
    if low in ("next week", "next_week", "nextweek"):
        return (today + datetime.timedelta(days=7)).isoformat()
    try:
        return datetime.date.fromisoformat(s).isoformat()
    except (ValueError, TypeError):
        raise HTTPException(400, f"invalid deadline_date: {v!r} (expected Today|Tomorrow|Next week|YYYY-MM-DD)")


def _ensure_rest_labels(con, uid, tid, labels):
    for entry in labels or []:
        name = str(entry)
        row = con.execute(
            "SELECT id FROM labels WHERE id=? AND user_id=? AND is_deleted=0", (name, uid)
        ).fetchone()
        if row:
            lid = row["id"]
        else:
            lrow = con.execute(
                "SELECT id FROM labels WHERE name=? AND user_id=? AND is_deleted=0",
                (name, uid),
            ).fetchone()
            if lrow:
                lid = lrow["id"]
            else:
                lid = new_id()
                con.execute("INSERT INTO labels(id,user_id,name) VALUES(?,?,?)", (lid, uid, name))
        con.execute("INSERT OR IGNORE INTO task_labels(task_id,label_id) VALUES(?,?)", (tid, lid))


# Stubs filled in by later tasks (Task 5/8); pinned tests only cover
# create/get/list + 401 + tmp- guard for this task.
@router.post("/api/v1/tasks/quick")
def quick_add(body: dict, request: Request, uid: str = Depends(require_user)):
    # Idempotency: return stored response when X-Request-Id repeats.
    rid = request.headers.get("x-request-id")
    con = _con()
    if rid:
        hit = con.execute("SELECT response FROM idempotency WHERE key=?", (rid,)).fetchone()
        if hit:
            return json.loads(hit["response"])
    text = body.get("text", "") if isinstance(body, dict) else ""
    if not text or not text.strip():
        raise HTTPException(400, "text required")
    # body.get("auto_reminder") accepted + ignored (V1)
    today_iso = datetime.date.today().isoformat()
    lang_req = body.get("lang", "auto") if isinstance(body, dict) else "auto"
    p = parse_quick_add(text, today_iso, lang_req)
    due_date = p["due_date"] or today_iso
    # Resolve project name -> id (auto-create); default inbox.
    if p["project"]:
        row = con.execute(
            "SELECT id FROM projects WHERE name=? AND user_id=? AND is_deleted=0",
            (p["project"], uid),
        ).fetchone()
        if row:
            pid = row["id"]
        else:
            pid = new_id()
            con.execute(
                "INSERT INTO projects(id,user_id,name) VALUES(?,?,?)", (pid, uid, p["project"])
            )
    else:
        pid = "inbox"
        con.execute("INSERT OR IGNORE INTO projects(id,user_id,name) VALUES('inbox',?,'Inbox')", (uid,))
    # Resolve section name -> id (auto-create under resolved project).
    sid = None
    if p["section"]:
        srow = con.execute(
            "SELECT id FROM sections WHERE project_id=? AND name=? AND is_deleted=0",
            (pid, p["section"]),
        ).fetchone()
        if srow:
            sid = srow["id"]
        else:
            sid = new_id()
            con.execute(
                "INSERT INTO sections(id,project_id,name) VALUES(?,?,?)", (sid, pid, p["section"])
            )
    # Resolve labels (auto-create) + task_labels.
    label_ids = []
    for name in p["labels"]:
        lrow = con.execute(
            "SELECT id FROM labels WHERE name=? AND user_id=? AND is_deleted=0",
            (name, uid),
        ).fetchone()
        if lrow:
            lid = lrow["id"]
        else:
            lid = new_id()
            con.execute("INSERT INTO labels(id,user_id,name) VALUES(?,?,?)", (lid, uid, name))
        label_ids.append((lid, name))
    tid = new_id()
    now = now_iso()
    con.execute(
        "INSERT INTO tasks(id,user_id,content,description,project_id,section_id,priority,due_date,due_string,due_lang,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (tid, uid, p["content"], "", pid, sid, p["priority"], due_date, text, p["lang"], now, now),
    )
    for lid, _name in label_ids:
        con.execute(
            "INSERT OR IGNORE INTO task_labels(task_id,label_id) VALUES(?,?)", (tid, lid)
        )
    con.commit()
    row = con.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    resp = _with_day_order(con, task_to_api(row, [n for _, n in label_ids]))
    if rid:
        con.execute(
            "INSERT OR IGNORE INTO idempotency(key,response) VALUES(?,?)",
            (rid, json.dumps(resp)),
        )
        con.commit()
    return resp


@router.post("/api/v1/tasks/{tid}")
def update_task(tid: str, body: dict, uid: str = Depends(require_user)):
    if tid.startswith("tmp-"):
        raise HTTPException(400, "Non-base32 digit found: tmp placeholder not valid")
    if not isinstance(body, dict):
        raise HTTPException(400, "invalid body")
    con = _con()
    r = con.execute("SELECT * FROM tasks WHERE id=? AND user_id=?", (tid, uid)).fetchone()
    if not r or r["is_deleted"]:
        raise HTTPException(404, "not found")
    sets, vals = [], []

    def _set(col, val):
        sets.append(f"{col}=?")
        vals.append(val)

    if "content" in body:
        v = body["content"]
        if v is None or (isinstance(v, str) and not v.strip()):
            raise HTTPException(400, "content required")
        _set("content", v)
    if "description" in body:
        v = body["description"]
        _set("description", "" if v is None else v)
    if "project_id" in body and body["project_id"] is not None:
        _set("project_id", body["project_id"])
    if "section_id" in body:
        _set("section_id", body.get("section_id"))
    if "parent_id" in body:
        _set("parent_id", body.get("parent_id"))
    if "priority" in body and body["priority"] is not None:
        try:
            _set("priority", int(body["priority"]))
        except (ValueError, TypeError):
            raise HTTPException(400, "invalid priority")
    for alias in ("responsible_uid", "assignee_id", "assignee"):
        if alias in body and body[alias] is not None:
            _set("responsible_uid", body[alias])
            break
    # Deadline: flat deadline_date or nested deadline dict.
    if "deadline_date" in body:
        v = body["deadline_date"]
        _set("deadline_date", None if v is None else _parse_deadline_value(v))
    elif "deadline" in body:
        dl = body["deadline"]
        if dl is None:
            _set("deadline_date", None)
        elif isinstance(dl, dict):
            d = dl.get("date")
            _set("deadline_date", None if d is None else _parse_deadline_value(d))
        elif isinstance(dl, str):
            _set("deadline_date", _parse_deadline_value(dl))
        else:
            raise HTTPException(400, "invalid deadline")
    # Due: nested dict merges (only provided keys), flat due_* keys update directly.
    if "due" in body:
        due = body["due"]
        if due is None:
            sets.append("due_date=NULL,due_datetime=NULL,due_timezone=NULL,due_string=NULL,due_lang='en',is_recurring=0")
        elif isinstance(due, dict):
            if "date" in due:
                _set("due_date", due["date"])
            if "datetime" in due:
                _set("due_datetime", due["datetime"])
            if "timezone" in due:
                _set("due_timezone", due["timezone"])
            if "string" in due:
                _set("due_string", due["string"])
            if "lang" in due:
                _set("due_lang", due["lang"] or "en")
            if "is_recurring" in due:
                _set("is_recurring", 1 if due["is_recurring"] else 0)
        else:
            raise HTTPException(400, "invalid due")
    for flat, col in (
        ("due_date", "due_date"),
        ("due_datetime", "due_datetime"),
        ("due_timezone", "due_timezone"),
        ("due_string", "due_string"),
        ("due_lang", "due_lang"),
        ("is_recurring", "is_recurring"),
    ):
        if flat in body:
            v = body[flat]
            if flat == "is_recurring":
                _set(col, 1 if v else 0)
            else:
                _set(col, v)
    # Duration: dict or flat keys.
    if "duration" in body:
        du = body["duration"]
        if du is None:
            sets.append("duration_amount=NULL,duration_unit=NULL")
        elif isinstance(du, dict):
            if "amount" in du:
                _set("duration_amount", du["amount"])
            if "unit" in du:
                _set("duration_unit", du["unit"] or "minute")
        elif isinstance(du, int):
            _set("duration_amount", du)
        else:
            raise HTTPException(400, "invalid duration")
    if "duration_amount" in body:
        _set("duration_amount", body["duration_amount"])
    if "duration_unit" in body:
        _set("duration_unit", body["duration_unit"])
    if "order_key" in body and body["order_key"] is not None:
        v = body["order_key"]
        if not isinstance(v, str) or not v.strip():
            raise HTTPException(400, "invalid order_key")
        _set("order_key", v)

    if sets:
        _set("updated_at", now_iso())
        con.execute(f"UPDATE tasks SET {','.join(sets)} WHERE id=? AND user_id=?", (*vals, tid, uid))
    if "labels" in body and body["labels"] is not None:
        if not isinstance(body["labels"], list):
            raise HTTPException(400, "invalid labels")
        con.execute("DELETE FROM task_labels WHERE task_id=?", (tid,))
        _ensure_rest_labels(con, uid, tid, body["labels"])
    con.commit()
    row = con.execute("SELECT * FROM tasks WHERE id=? AND user_id=?", (tid, uid)).fetchone()
    return _with_day_order(con, task_to_api(row, _labels(con, tid)))


@router.post("/api/v1/tasks/{tid}/close")
def close_task(tid: str, uid: str = Depends(require_user)):
    if tid.startswith("tmp-"):
        raise HTTPException(400, "Non-base32 digit found: tmp placeholder not valid")
    con = _con()
    r = con.execute("SELECT * FROM tasks WHERE id=? AND user_id=?", (tid, uid)).fetchone()
    if not r or r["is_deleted"]:
        raise HTTPException(404, "not found")
    now = now_iso()
    con.execute("UPDATE tasks SET completed=1,updated_at=? WHERE id=? AND user_id=?", (now, tid, uid))
    # Hide direct children as well; no recurrence expansion (no fake recurrence).
    con.execute("UPDATE tasks SET completed=1,updated_at=? WHERE parent_id=? AND user_id=?", (now, tid, uid))
    con.commit()
    row = con.execute("SELECT * FROM tasks WHERE id=? AND user_id=?", (tid, uid)).fetchone()
    return _with_day_order(con, task_to_api(row, _labels(con, tid)))


@router.post("/api/v1/tasks/{tid}/reopen")
def reopen_task(tid: str, uid: str = Depends(require_user)):
    if tid.startswith("tmp-"):
        raise HTTPException(400, "Non-base32 digit found: tmp placeholder not valid")
    con = _con()
    r = con.execute("SELECT * FROM tasks WHERE id=? AND user_id=?", (tid, uid)).fetchone()
    if not r or r["is_deleted"]:
        raise HTTPException(404, "not found")
    now = now_iso()
    con.execute("UPDATE tasks SET completed=0,updated_at=? WHERE id=? AND user_id=?", (now, tid, uid))
    con.commit()
    row = con.execute("SELECT * FROM tasks WHERE id=? AND user_id=?", (tid, uid)).fetchone()
    return _with_day_order(con, task_to_api(row, _labels(con, tid)))


@router.post("/api/v1/tasks/{tid}/move")
def move_task(tid: str, body: dict | None = None, uid: str = Depends(require_user)):
    if tid.startswith("tmp-"):
        raise HTTPException(400, "Non-base32 digit found: tmp placeholder not valid")
    if body is None:
        body = {}
    if not isinstance(body, dict):
        raise HTTPException(400, "invalid body")
    con = _con()
    r = con.execute("SELECT * FROM tasks WHERE id=? AND user_id=?", (tid, uid)).fetchone()
    if not r or r["is_deleted"]:
        raise HTTPException(404, "not found")
    sets, vals = [], []
    if body.get("project_id"):
        sets.append("project_id=?")
        vals.append(body["project_id"])
    if "section_id" in body:
        sets.append("section_id=?")
        vals.append(body.get("section_id"))
    if "parent_id" in body:
        sets.append("parent_id=?")
        vals.append(body.get("parent_id"))
    if body.get("order_key") is not None:
        v = body.get("order_key")
        if not isinstance(v, str) or not v.strip():
            raise HTTPException(400, "invalid order_key")
        sets.append("order_key=?")
        vals.append(v)
    if sets:
        sets.append("updated_at=?")
        vals.append(now_iso())
        con.execute(f"UPDATE tasks SET {','.join(sets)} WHERE id=? AND user_id=?", (*vals, tid, uid))
        con.commit()
    row = con.execute("SELECT * FROM tasks WHERE id=? AND user_id=?", (tid, uid)).fetchone()
    return _with_day_order(con, task_to_api(row, _labels(con, tid)))


@router.post("/api/v1/tasks/{tid}/duplicate")
def duplicate_task(tid: str, uid: str = Depends(require_user)):
    # Duplicate without comments/reminders: copy content/description/project/
    # priority/labels/due/deadline/duration/section/responsible/parent only.
    if tid.startswith("tmp-"):
        raise HTTPException(400, "Non-base32 digit found: tmp placeholder not valid")
    con = _con()
    r = con.execute("SELECT * FROM tasks WHERE id=? AND user_id=?", (tid, uid)).fetchone()
    if not r or r["is_deleted"]:
        raise HTTPException(404, "not found")
    nid = new_id()
    now = now_iso()
    fresh_key = _fresh_order_key(r["order_key"] if "order_key" in r.keys() else "a0", nid)
    con.execute(
        "INSERT INTO tasks(id,user_id,content,description,project_id,section_id,parent_id,"
        "priority,due_date,due_datetime,due_timezone,due_string,due_lang,is_recurring,"
        "deadline_date,duration_amount,duration_unit,responsible_uid,order_key,created_at,updated_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            nid, uid, r["content"], r["description"] or "", r["project_id"],
            r["section_id"], r["parent_id"], r["priority"],
            r["due_date"], r["due_datetime"], r["due_timezone"], r["due_string"],
            r["due_lang"] or "en", r["is_recurring"] or 0,
            r["deadline_date"], r["duration_amount"], r["duration_unit"],
            r["responsible_uid"], fresh_key, now, now,
        ),
    )
    for (lid,) in con.execute("SELECT label_id FROM task_labels WHERE task_id=?", (tid,)).fetchall():
        con.execute("INSERT OR IGNORE INTO task_labels(task_id,label_id) VALUES(?,?)", (nid, lid))
    # Explicitly no comments/reminders copy: reminders table untouched for nid.
    con.commit()
    row = con.execute("SELECT * FROM tasks WHERE id=? AND user_id=?", (nid, uid)).fetchone()
    return _with_day_order(con, task_to_api(row, _labels(con, nid)))


@router.delete("/api/v1/tasks/{tid}")
def delete_task(tid: str, uid: str = Depends(require_user)):
    if tid.startswith("tmp-"):
        raise HTTPException(400, "Non-base32 digit found: tmp placeholder not valid")
    con = _con()
    r = con.execute("SELECT * FROM tasks WHERE id=? AND user_id=?", (tid, uid)).fetchone()
    if not r:
        raise HTTPException(404, "not found")
    con.execute("UPDATE tasks SET is_deleted=1,updated_at=? WHERE id=? AND user_id=?", (now_iso(), tid, uid))
    con.commit()
    return {"ok": True}
