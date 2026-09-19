import datetime
import json
import os
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


@router.post("/api/v1/tasks")
def create_task(body: dict, uid: str = Depends(require_user)):
    if not body.get("content"):
        raise HTTPException(400, "content required")
    con = _con()
    tid = new_id()
    now = now_iso()
    pid = body.get("project_id", "inbox")
    con.execute("INSERT INTO tasks(id,user_id,content,description,project_id,section_id,parent_id,priority,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (tid, uid, body["content"], body.get("description", ""), pid, body.get("section_id"), body.get("parent_id"), body.get("priority", 1), now, now))
    con.commit()
    row = con.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    return task_to_api(row, [])


@router.get("/api/v1/tasks")
def list_tasks(uid: str = Depends(require_user)):
    con = _con()
    rows = con.execute("SELECT * FROM tasks WHERE user_id=? AND completed=0 AND is_deleted=0", (uid,)).fetchall()
    return {"results": [task_to_api(r, _labels(con, r["id"])) for r in rows]}


@router.get("/api/v1/tasks/{tid}")
def get_task(tid: str, uid: str = Depends(require_user)):
    if tid.startswith("tmp-"):
        raise HTTPException(400, "Non-base32 digit found: tmp placeholder not valid")
    con = _con()
    r = con.execute("SELECT * FROM tasks WHERE id=? AND user_id=?", (tid, uid)).fetchone()
    if not r:
        raise HTTPException(404, "not found")
    return task_to_api(r, _labels(con, tid))


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
    p = parse_quick_add(text, today_iso)
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
        (tid, uid, p["content"], "", pid, sid, p["priority"], due_date, text, "en", now, now),
    )
    for lid, _name in label_ids:
        con.execute(
            "INSERT OR IGNORE INTO task_labels(task_id,label_id) VALUES(?,?)", (tid, lid)
        )
    con.commit()
    row = con.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    resp = task_to_api(row, [n for _, n in label_ids])
    if rid:
        con.execute(
            "INSERT OR IGNORE INTO idempotency(key,response) VALUES(?,?)",
            (rid, json.dumps(resp)),
        )
        con.commit()
    return resp


@router.post("/api/v1/tasks/{tid}")
def update_task(tid: str, uid: str = Depends(require_user)):
    raise HTTPException(501, "not implemented")


@router.post("/api/v1/tasks/{tid}/close")
def close_task(tid: str, uid: str = Depends(require_user)):
    raise HTTPException(501, "not implemented")


@router.post("/api/v1/tasks/{tid}/reopen")
def reopen_task(tid: str, uid: str = Depends(require_user)):
    raise HTTPException(501, "not implemented")


@router.post("/api/v1/tasks/{tid}/move")
def move_task(tid: str, uid: str = Depends(require_user)):
    raise HTTPException(501, "not implemented")


@router.delete("/api/v1/tasks/{tid}")
def delete_task(tid: str, uid: str = Depends(require_user)):
    raise HTTPException(501, "not implemented")
