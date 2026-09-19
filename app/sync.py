"""Sync read + write paths for OpenDoist V1 (Tasks 4-5)."""
import datetime
import json
import urllib.parse

from fastapi import APIRouter, Depends, Request
from app.auth import require_user
from app.db import idempotency_get, idempotency_put
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


def _parse_commands(raw):
    if raw is None:
        return []
    if isinstance(raw, list):
        return [c for c in raw if isinstance(c, dict)]
    s = str(raw).strip()
    if not s:
        return []
    try:
        v = json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return []
    if isinstance(v, dict):
        v = [v]
    if not isinstance(v, list):
        return []
    return [c for c in v if isinstance(c, dict)]


def _bump_ts(ts, seconds=1):
    # now_iso() has 1s resolution; chain writes strictly above the
    # incoming token baseline so same-second writes stay visible to the
    # incremental `updated_at > since` rescan in this response.
    dt = datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ") + datetime.timedelta(
        seconds=seconds
    )
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_ref(ref, temp_map):
    # Remap temp_ids from earlier commands in the same batch to real ids.
    if ref is not None and not isinstance(ref, str):
        ref = str(ref)
    if isinstance(ref, str) and ref in temp_map:
        return temp_map[ref]
    return ref


def _ensure_labels(con, uid, tid, labels):
    # Accept label names or ids; auto-create by name when missing.
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
                con.execute(
                    "INSERT INTO labels(id,user_id,name) VALUES(?,?,?)", (lid, uid, name)
                )
        con.execute(
            "INSERT OR IGNORE INTO task_labels(task_id,label_id) VALUES(?,?)", (tid, lid)
        )


def _due_columns(due):
    # Map a Todoist due dict onto task columns.
    cols = {}
    if not isinstance(due, dict):
        return cols
    if "date" in due:
        cols["due_date"] = due["date"]
    if "datetime" in due:
        cols["due_datetime"] = due["datetime"]
    if "timezone" in due:
        cols["due_timezone"] = due["timezone"]
    if "string" in due:
        cols["due_string"] = due["string"]
    if "lang" in due:
        cols["due_lang"] = due["lang"] or "en"
    if "is_recurring" in due:
        cols["is_recurring"] = 1 if due["is_recurring"] else 0
    return cols


def _exec_item_add(con, uid, args, temp_map, now):
    content = (args.get("content") or "").strip() if isinstance(args.get("content"), str) else args.get("content")
    if not content:
        raise ValueError("content required")
    tid = new_id()
    pid = args.get("project_id") or "inbox"
    parent = _resolve_ref(args.get("parent_id"), temp_map)
    due = _due_columns(args.get("due") or {})
    deadline = args.get("deadline") or {}
    duration = args.get("duration") or {}
    con.execute(
        "INSERT INTO tasks(id,user_id,content,description,project_id,section_id,parent_id,priority,"
        "due_date,due_datetime,due_timezone,due_string,due_lang,is_recurring,"
        "deadline_date,duration_amount,duration_unit,responsible_uid,created_at,updated_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            tid, uid, content, args.get("description") or "", pid,
            args.get("section_id"), parent, args.get("priority", 1),
            due.get("due_date"), due.get("due_datetime"), due.get("due_timezone"),
            due.get("due_string"), due.get("due_lang", "en"), due.get("is_recurring", 0),
            deadline.get("date") if isinstance(deadline, dict) else None,
            duration.get("amount") if isinstance(duration, dict) else None,
            (duration.get("unit") or "minute") if isinstance(duration, dict) else None,
            args.get("responsible_uid"), now, now,
        ),
    )
    _ensure_labels(con, uid, tid, args.get("labels"))
    return tid


def _exec_item_update(con, uid, args, temp_map, now):
    tid = _resolve_ref(args.get("id"), temp_map)
    if not tid:
        raise ValueError("id required")
    row = con.execute("SELECT * FROM tasks WHERE id=? AND user_id=?", (tid, uid)).fetchone()
    if not row:
        raise ValueError("not found")
    sets, vals = [], []
    for key in ("content", "description", "project_id", "section_id", "priority", "responsible_uid"):
        if key in args and args[key] is not None:
            sets.append(f"{key}=?")
            vals.append(args[key])
    if "parent_id" in args:
        sets.append("parent_id=?")
        vals.append(_resolve_ref(args.get("parent_id"), temp_map))
    if "due" in args:
        # Partial merge: only provided due keys change; timezone/string
        # survive unless explicitly overwritten. `due: null` clears.
        if args["due"] is None:
            sets.append("due_date=NULL,due_datetime=NULL,due_timezone=NULL,due_string=NULL,due_lang='en',is_recurring=0")
        else:
            for col, val in _due_columns(args["due"]).items():
                sets.append(f"{col}=?")
                vals.append(val)
    if "deadline" in args:
        dl = args["deadline"]
        sets.append("deadline_date=?")
        vals.append(dl.get("date") if isinstance(dl, dict) else dl)
    if "duration" in args:
        du = args["duration"] or {}
        if isinstance(du, dict):
            if "amount" in du:
                sets.append("duration_amount=?")
                vals.append(du["amount"])
            if "unit" in du:
                sets.append("duration_unit=?")
                vals.append(du["unit"] or "minute")
    if sets:
        sets.append("updated_at=?")
        vals.append(now)
        con.execute(f"UPDATE tasks SET {','.join(sets)} WHERE id=? AND user_id=?", (*vals, tid, uid))
    if "labels" in args and args["labels"] is not None:
        con.execute("DELETE FROM task_labels WHERE task_id=?", (tid,))
        _ensure_labels(con, uid, tid, args["labels"])


def _exec_item_move(con, uid, args, temp_map, now):
    tid = _resolve_ref(args.get("id"), temp_map)
    if not tid:
        raise ValueError("id required")
    row = con.execute("SELECT * FROM tasks WHERE id=? AND user_id=?", (tid, uid)).fetchone()
    if not row:
        raise ValueError("not found")
    sets, vals = [], []
    if args.get("project_id"):
        sets.append("project_id=?")
        vals.append(args["project_id"])
    if "section_id" in args:
        sets.append("section_id=?")
        vals.append(args.get("section_id"))
    if "parent_id" in args:
        sets.append("parent_id=?")
        vals.append(_resolve_ref(args.get("parent_id"), temp_map))
    if sets:
        sets.append("updated_at=?")
        vals.append(now)
        con.execute(f"UPDATE tasks SET {','.join(sets)} WHERE id=? AND user_id=?", (*vals, tid, uid))


def _exec_item_close(con, uid, args, temp_map, now):
    tid = args.get("id")
    if not tid:
        raise ValueError("id required")
    row = con.execute("SELECT * FROM tasks WHERE id=? AND user_id=?", (tid, uid)).fetchone()
    if not row:
        raise ValueError("not found")
    con.execute("UPDATE tasks SET completed=1,updated_at=? WHERE id=? AND user_id=?", (now, tid, uid))
    # Hide children of the closed item as well.
    con.execute(
        "UPDATE tasks SET completed=1,updated_at=? WHERE parent_id=? AND user_id=?", (now, tid, uid)
    )


def _exec_item_delete(con, uid, args, temp_map, now):
    tid = args.get("id")
    if not tid:
        raise ValueError("id required")
    row = con.execute("SELECT * FROM tasks WHERE id=? AND user_id=?", (tid, uid)).fetchone()
    if not row:
        raise ValueError("not found")
    con.execute("UPDATE tasks SET is_deleted=1,updated_at=? WHERE id=? AND user_id=?", (now, tid, uid))


def _exec_day_orders(con, args, temp_map, today):
    mapping = args.get("ids_to_orders", args)
    pairs = mapping.items() if isinstance(mapping, dict) else mapping
    for task_id, ord in pairs:
        task_id = _resolve_ref(task_id, temp_map)
        con.execute(
            "INSERT INTO day_orders(task_id,day,ord) VALUES(?,?,?)"
            " ON CONFLICT(task_id,day) DO UPDATE SET ord=excluded.ord",
            (task_id, today, int(ord)),
        )


def _exec_reminder_add(con, args, temp_map):
    task_id = _resolve_ref(args.get("item_id", args.get("task_id", args.get("id"))), temp_map)
    if not task_id:
        raise ValueError("item_id required")
    row = con.execute("SELECT id FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        raise ValueError("not found")
    rid = new_id()
    con.execute(
        "INSERT INTO reminders(id,task_id,minute_offset,due_string) VALUES(?,?,?,?)",
        (rid, task_id, args.get("minute_offset"), args.get("due_string")),
    )
    return rid


_EXECUTORS = {
    "item_add": _exec_item_add,
    "item_update": _exec_item_update,
    "item_move": _exec_item_move,
    "item_close": _exec_item_close,
    "item_delete": _exec_item_delete,
}


def _process_commands(con, uid, commands, today, since=None):
    sync_status, temp_id_mapping = {}, {}
    last = since
    # Max 100 per batch; caller chains the remainder with the next token.
    for cmd in commands[:100]:
        if not isinstance(cmd, dict):
            continue
        uuid = str(cmd.get("uuid") or new_id())
        if uuid in sync_status:
            continue
        hit = idempotency_get(con, uuid)
        if hit is not None:
            try:
                stored = json.loads(hit)
            except (json.JSONDecodeError, ValueError):
                stored = {"status": "ok"}
            sync_status[uuid] = stored.get("status", "ok")
            if stored.get("temp_id") and stored.get("real_id"):
                temp_id_mapping[stored["temp_id"]] = stored["real_id"]
            continue
        ctype, args = cmd.get("type"), cmd.get("args") or {}
        if not isinstance(args, dict):
            args = {}
        now = now_iso()
        if last is not None and now <= last:
            now = _bump_ts(last)
        last = now
        try:
            real_id = None
            if ctype == "item_add":
                real_id = _EXECUTORS[ctype](con, uid, args, temp_id_mapping, now)
                temp_id = cmd.get("temp_id")
                if temp_id:
                    temp_id_mapping[str(temp_id)] = real_id
            elif ctype in _EXECUTORS:
                _EXECUTORS[ctype](con, uid, args, temp_id_mapping, now)
            elif ctype == "item_update_day_orders":
                _exec_day_orders(con, args, temp_id_mapping, today)
            elif ctype == "reminder_add":
                _exec_reminder_add(con, args, temp_id_mapping)
            else:
                raise ValueError(f"unknown command: {ctype}")
            status = "ok"
        except Exception as exc:  # noqa: BLE001 - surfaced per-uuid in sync_status
            status = {"error": str(exc)}
        sync_status[uuid] = status
        temp_id = cmd.get("temp_id") if ctype == "item_add" else None
        idempotency_put(
            con, uuid,
            json.dumps({"status": status, "temp_id": temp_id, "real_id": real_id}),
        )
    return sync_status, temp_id_mapping


@router.post("/api/v1/sync")
async def sync_read(request: Request, uid: str = Depends(require_user)):
    ctype = request.headers.get("content-type", "")
    sync_token = "*"
    resource_types_raw = None
    commands_raw = None
    if "application/x-www-form-urlencoded" in ctype:
        raw = (await request.body()).decode("utf-8", "replace")
        fields = urllib.parse.parse_qs(raw, keep_blank_values=True)
        sync_token = (fields.get("sync_token", ["*"])[0] or "*")
        rt_vals = fields.get("resource_types")
        resource_types_raw = rt_vals[0] if rt_vals else None
        cmd_vals = fields.get("commands")
        commands_raw = cmd_vals[0] if cmd_vals else None
    elif "multipart/form-data" in ctype:
        form = await request.form()
        sync_token = str(form.get("sync_token", "*") or "*")
        resource_types_raw = form.get("resource_types")
        commands_raw = form.get("commands")
    else:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if isinstance(body, dict):
            sync_token = str(body.get("sync_token", "*") or "*")
            rt = body.get("resource_types")
            resource_types_raw = json.dumps(rt) if isinstance(rt, list) else rt
            cmds = body.get("commands")
            commands_raw = json.dumps(cmds) if isinstance(cmds, list) else cmds
        # Also accept query/form fallback for robustness.
        if sync_token == "*":
            sync_token = str(request.query_params.get("sync_token", "*") or "*")
    resource_types = _parse_resource_types(resource_types_raw)
    commands = _parse_commands(commands_raw)

    con = _shared_con()
    today = datetime.date.today().isoformat()
    is_full = sync_token == "*"

    # Resolve incremental baseline: token -> created_at in sync_state.
    since = None
    if not is_full:
        row = con.execute("SELECT created_at FROM sync_state WHERE token=?", (sync_token,)).fetchone()
        if row:
            since = row["created_at"]

    sync_status, temp_id_mapping = (
        _process_commands(con, uid, commands, today, since) if commands else ({}, {})
    )

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
        "temp_id_mapping": temp_id_mapping,
        "sync_status": sync_status,
        "sync_token": new_token,
        "full_sync": is_full,
    }
