import os
from fastapi import APIRouter, Depends, HTTPException
from app.auth import require_user
from app.db import SCHEMA, get_db
from app.models import new_id, now_iso, task_to_api

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
            _mem_con.execute("INSERT OR IGNORE INTO projects(id,name) VALUES('inbox','Inbox')")
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
