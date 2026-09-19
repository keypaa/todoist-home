"""Sync read path for OpenDoist V1 (Task 4)."""
import datetime
import json
import urllib.parse

from fastapi import APIRouter, Depends, Request
from app.auth import require_user
from app.models import new_id, now_iso, task_to_api

router = APIRouter()


def _shared_con():
    # Reuse api_tasks' process-wide :memory: connection so sync sees the
    # same rows the REST routes created in tests. Import locally to avoid
    # a hard import cycle at module load (main imports both routers).
    from app.api_tasks import _con as _tasks_con

    return _tasks_con()


def _labels(con, tid):
    from app.api_tasks import _labels as _task_labels

    return _task_labels(con, tid)


def _parse_resource_types(raw):
    if raw is None:
        return ["all"]
    if isinstance(raw, list):
        return raw
    s = str(raw).strip()
    if not s:
        return ["all"]
    try:
        v = json.loads(s)
        if isinstance(v, list):
            return [str(x) for x in v]
        return [str(v)]
    except (json.JSONDecodeError, ValueError):
        # Fallback: comma-separated single string.
        return [p.strip().strip('"\'') for p in s.split(",") if p.strip()]


@router.post("/api/v1/sync")
async def sync_read(request: Request, uid: str = Depends(require_user)):
    ctype = request.headers.get("content-type", "")
    sync_token = "*"
    resource_types_raw = None
    if "application/x-www-form-urlencoded" in ctype:
        raw = (await request.body()).decode("utf-8", "replace")
        fields = urllib.parse.parse_qs(raw, keep_blank_values=True)
        sync_token = (fields.get("sync_token", ["*"])[0] or "*")
        rt_vals = fields.get("resource_types")
        resource_types_raw = rt_vals[0] if rt_vals else None
    elif "multipart/form-data" in ctype:
        form = await request.form()
        sync_token = str(form.get("sync_token", "*") or "*")
        resource_types_raw = form.get("resource_types")
    else:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if isinstance(body, dict):
            sync_token = str(body.get("sync_token", "*") or "*")
            rt = body.get("resource_types")
            resource_types_raw = json.dumps(rt) if isinstance(rt, list) else rt
        # Also accept query/form fallback for robustness.
        if sync_token == "*":
            sync_token = str(request.query_params.get("sync_token", "*") or "*")
    resource_types = _parse_resource_types(resource_types_raw)

    con = _shared_con()
    today = datetime.date.today().isoformat()
    is_full = sync_token == "*"

    # Resolve incremental baseline: token -> created_at in sync_state.
    since = None
    if not is_full:
        row = con.execute("SELECT created_at FROM sync_state WHERE token=?", (sync_token,)).fetchone()
        if row:
            since = row["created_at"]

    # Projects (non-archived, non-deleted, user-scoped).
    prows = con.execute(
        "SELECT * FROM projects WHERE user_id=? AND is_deleted=0 AND is_archived=0", (uid,)
    ).fetchall()
    projects = [
        {"id": r["id"], "name": r["name"], "is_archived": False, "is_deleted": False,
         "order_key": r["order_key"] if "order_key" in r.keys() else "a0"}
        for r in prows
    ]
    # Sections (non-archived, non-deleted).
    srows = con.execute(
        "SELECT * FROM sections WHERE is_deleted=0 AND is_archived=0"
    ).fetchall()
    sections = [
        {"id": r["id"], "project_id": r["project_id"], "name": r["name"],
         "is_archived": False, "is_deleted": False}
        for r in srows
    ]
    # Labels (non-deleted, user-scoped).
    lrows = con.execute(
        "SELECT * FROM labels WHERE user_id=? AND is_deleted=0", (uid,)
    ).fetchall()
    labels = [{"id": r["id"], "name": r["name"], "is_deleted": False} for r in lrows]

    # Items.
    if is_full or since is None:
        trows = con.execute(
            "SELECT * FROM tasks WHERE user_id=? AND completed=0 AND is_deleted=0", (uid,)
        ).fetchall()
        items = []
        for r in trows:
            d = task_to_api(r, _labels(con, r["id"]))
            do = con.execute(
                "SELECT ord FROM day_orders WHERE task_id=? AND day=?", (r["id"], today)
            ).fetchone()
            d["day_order"] = do["ord"] if do else 0
            items.append(d)
    else:
        # Incremental: full rescan filtered by updated_at + tombstones.
        trows = con.execute(
            "SELECT * FROM tasks WHERE user_id=? AND updated_at>?", (uid, since)
        ).fetchall()
        items = []
        for r in trows:
            if r["is_deleted"]:
                items.append({"id": r["id"], "is_deleted": True})
                continue
            if r["completed"]:
                continue
            d = task_to_api(r, _labels(con, r["id"]))
            do = con.execute(
                "SELECT ord FROM day_orders WHERE task_id=? AND day=?", (r["id"], today)
            ).fetchone()
            d["day_order"] = do["ord"] if do else 0
            items.append(d)

    # day_orders for today.
    dorows = con.execute("SELECT task_id, ord FROM day_orders WHERE day=?", (today,)).fetchall()
    day_orders = {r["task_id"]: r["ord"] for r in dorows}

    new_token = new_id()
    now = now_iso()
    con.execute(
        "INSERT OR IGNORE INTO sync_state(token,created_at) VALUES(?,?)", (new_token, now)
    )
    con.commit()

    _ = resource_types  # V1: always return full shape regardless of subset.
    return {
        "user": {"id": "1", "email": "local@opendoist"},
        "projects": projects,
        "items": items,
        "sections": sections,
        "labels": labels,
        "collaborators": [],
        "reminders": [],
        "completed_info": [],
        "day_orders": day_orders,
        "filters": [],
        "temp_id_mapping": {},
        "sync_status": {},
        "sync_token": new_token,
        "full_sync": is_full,
    }
