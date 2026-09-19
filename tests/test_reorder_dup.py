# tests/test_reorder_dup.py
import datetime
import json
import os
os.environ["OPENDOIST_DB"] = ":memory:"
from fastapi.testclient import TestClient
from app.main import app

H = {"Authorization": "Bearer x"}


def _sync(c, token, cmds):
    return c.post(
        "/api/v1/sync",
        data={
            "sync_token": token,
            "resource_types": '["all"]',
            "commands": json.dumps(cmds),
        },
        headers=H,
    )


def test_day_order_and_duplicate():
    c = TestClient(app)
    a = c.post("/api/v1/tasks/quick", json={"text": "A today"}, headers=H).json()["id"]
    cmds = [{"type": "item_update_day_orders", "uuid": "r1", "args": {"ids_to_orders": {a: 1}}}]
    r = c.post("/api/v1/sync", data={"sync_token": "*", "resource_types": '["all"]', "commands": json.dumps(cmds)}, headers=H)
    assert r.json()["sync_status"]["r1"] == "ok"


def test_day_orders_per_day_and_today_join():
    c = TestClient(app)
    tid = c.post("/api/v1/tasks", json={"content": "per-day task"}, headers=H).json()["id"]
    day = "2026-09-20"
    r = _sync(c, "*", [{"type": "item_update_day_orders", "uuid": "pd-1",
                        "args": {"day": day, "ids_to_orders": {tid: 7}}}])
    assert r.json()["sync_status"]["pd-1"] == "ok", r.text
    j = r.json()
    today = datetime.date.today().isoformat()
    # Non-today write must be stored under that day and observable via
    # day_orders_by_day, not conflated into today's flat map.
    assert "day_orders_by_day" in j, j.keys()
    assert j["day_orders_by_day"].get(day, {}).get(tid) == 7, j["day_orders_by_day"]
    if day != today:
        assert j["day_orders"].get(tid) != 7, j["day_orders"]
    # today ordering still joins: set today order and verify items join
    r2 = _sync(c, j["sync_token"], [{"type": "item_update_day_orders", "uuid": "pd-2",
                                     "args": {"ids_to_orders": {tid: 3}}}])
    assert r2.json()["sync_status"]["pd-2"] == "ok"
    items = {i["id"]: i for i in r2.json()["items"] if "content" in i}
    assert items[tid]["day_order"] == 3, items[tid]
    assert r2.json()["day_orders"].get(tid) == 3


def test_upcoming_day_order_observable_per_task_day():
    c = TestClient(app)
    today = datetime.date.today().isoformat()
    day = (datetime.date.today() + datetime.timedelta(days=5)).isoformat()
    assert day != today
    tid = c.post("/api/v1/tasks", json={"content": "upcoming reorder", "due": {"date": day}}, headers=H).json()["id"]
    r = _sync(c, "*", [{"type": "item_update_day_orders", "uuid": "up-1",
                        "args": {"day": day, "ids_to_orders": {tid: 7}}}])
    assert r.json()["sync_status"]["up-1"] == "ok", r.text
    j = r.json()
    # Upcoming write observable in per-day map, not today's flat map.
    assert j["day_orders_by_day"].get(day, {}).get(tid) == 7, j
    assert j["day_orders"].get(tid) != 7, j["day_orders"]
    # Sync items join per-task day (due_date), so Upcoming reorder works.
    items = {i["id"]: i for i in j["items"] if "content" in i}
    assert items[tid]["day_order"] == 7, items[tid]
    # REST joins per-task day (due_date) as well.
    got = c.get(f"/api/v1/tasks/{tid}", headers=H).json()
    assert got["day_order"] == 7, got
    lst = c.get("/api/v1/tasks", headers=H).json()["results"]
    lmap = {t["id"]: t for t in lst}
    assert lmap[tid]["day_order"] == 7, lmap[tid]


def test_inbox_fractional_reorder_scoped():
    c = TestClient(app)
    t1 = c.post("/api/v1/tasks", json={"content": "R1", "project_id": "inbox"}, headers=H).json()["id"]
    t2 = c.post("/api/v1/tasks", json={"content": "R2", "project_id": "inbox"}, headers=H).json()["id"]
    # fractional order_key via sync item_update
    r = _sync(c, "*", [
        {"type": "item_update", "uuid": "rk-1", "args": {"id": t1, "order_key": "a0"}},
        {"type": "item_update", "uuid": "rk-2", "args": {"id": t2, "order_key": "a1"}},
    ])
    assert r.json()["sync_status"]["rk-1"] == "ok", r.text
    assert r.json()["sync_status"]["rk-2"] == "ok", r.text
    g1 = c.get(f"/api/v1/tasks/{t1}", headers=H).json()
    g2 = c.get(f"/api/v1/tasks/{t2}", headers=H).json()
    assert g1["order_key"] == "a0", g1
    assert g2["order_key"] == "a1", g2
    assert g1["order_key"] < g2["order_key"]
    # reorder: swap via fractional key between them
    r2 = _sync(c, r.json()["sync_token"], [
        {"type": "item_update", "uuid": "rk-3", "args": {"id": t1, "order_key": "a2"}},
    ])
    assert r2.json()["sync_status"]["rk-3"] == "ok"
    assert c.get(f"/api/v1/tasks/{t1}", headers=H).json()["order_key"] == "a2"


def test_reorder_hidden_siblings_preserved_and_rollback():
    c = TestClient(app)
    va = c.post("/api/v1/tasks", json={"content": "VA"}, headers=H).json()["id"]
    vb = c.post("/api/v1/tasks", json={"content": "VB"}, headers=H).json()["id"]
    hid = c.post("/api/v1/tasks", json={"content": "HID"}, headers=H).json()["id"]
    # set known keys
    r = _sync(c, "*", [
        {"type": "item_update", "uuid": "hb-1", "args": {"id": va, "order_key": "b0"}},
        {"type": "item_update", "uuid": "hb-2", "args": {"id": vb, "order_key": "b1"}},
        {"type": "item_update", "uuid": "hb-3", "args": {"id": hid, "order_key": "b9"}},
    ])
    assert all(v == "ok" for v in r.json()["sync_status"].values()), r.text
    # hide one sibling (close) + delete another
    c.post(f"/api/v1/tasks/{hid}/close", headers=H)
    dc = c.post("/api/v1/tasks", json={"content": "DEL"}, headers=H).json()["id"]
    _sync(c, r.json()["sync_token"], [
        {"type": "item_update", "uuid": "hb-4", "args": {"id": dc, "order_key": "b8"}},
    ])
    c.delete(f"/api/v1/tasks/{dc}", headers=H)
    before_hidden = c.get(f"/api/v1/tasks/{hid}", headers=H)
    # reorder visible siblings; hidden keys must not move
    r2 = _sync(c, "*", [
        {"type": "item_update", "uuid": "hb-5", "args": {"id": va, "order_key": "b2"}},
        {"type": "item_update", "uuid": "hb-6", "args": {"id": "missing-id-xyz", "order_key": "b3"}},
    ])
    j2 = r2.json()
    assert j2["sync_status"]["hb-5"] == "ok", j2
    assert isinstance(j2["sync_status"]["hb-6"], dict) and "error" in j2["sync_status"]["hb-6"], j2
    # valid reorder persisted, failure did not roll back the good one, nor touch hidden
    assert c.get(f"/api/v1/tasks/{va}", headers=H).json()["order_key"] == "b2"
    # hidden sibling preserved (close keeps row; order_key untouched by reorder)
    from app.api_tasks import _con as _tasks_con
    con = _tasks_con()
    row = con.execute("SELECT order_key FROM tasks WHERE id=?", (hid,)).fetchone()
    assert row["order_key"] == "b9", dict(row)
    row2 = con.execute("SELECT order_key FROM tasks WHERE id=?", (dc,)).fetchone()
    assert row2["order_key"] == "b8", dict(row2)


def test_duplicate_copies_without_comments_reminders():
    c = TestClient(app)
    src = c.post("/api/v1/tasks", json={
        "content": "orig task",
        "description": "orig desc",
        "project_id": "inbox",
        "priority": 4,
        "labels": ["dup1"],
        "due": {"date": "2026-10-01", "string": "Oct 1", "timezone": "Europe/Berlin"},
        "deadline_date": "2026-10-05",
        "duration": {"amount": 30, "unit": "minute"},
    }, headers=H).json()
    sid = src["id"]
    # add a reminder to source (sync) — duplicate must NOT copy it
    r = _sync(c, "*", [{"type": "reminder_add", "uuid": "dup-r1",
                        "args": {"item_id": sid, "minute_offset": 15}}])
    assert r.json()["sync_status"]["dup-r1"] == "ok", r.text
    d = c.post(f"/api/v1/tasks/{sid}/duplicate", headers=H)
    assert d.status_code == 200, d.text
    dup = d.json()
    assert dup["id"] != sid
    assert dup["content"] == "orig task"
    assert dup["description"] == "orig desc"
    assert dup["project_id"] == src["project_id"]
    assert dup["priority"] == 4
    assert "dup1" in dup["labels"]
    assert dup["due"]["date"] == "2026-10-01"
    assert dup["deadline"]["date"] == "2026-10-05"
    assert dup["duration"]["amount"] == 30
    # Fresh fractional key: no sort collision with source.
    assert dup["order_key"] != src["order_key"], (dup, src)
    assert dup["order_key"] > src["order_key"], (dup, src)
    # no comments/reminders copied: new task has zero reminders
    from app.api_tasks import _con as _tasks_con
    con = _tasks_con()
    rows = con.execute("SELECT * FROM reminders WHERE task_id=? AND is_deleted=0", (dup["id"],)).fetchall()
    assert len(rows) == 0, [dict(x) for x in rows]
    # source still has its reminder
    srows = con.execute("SELECT * FROM reminders WHERE task_id=? AND is_deleted=0", (sid,)).fetchall()
    assert len(srows) == 1


def test_duplicate_via_sync_item_add_chain():
    c = TestClient(app)
    src = c.post("/api/v1/tasks", json={
        "content": "chain src",
        "description": "chain desc",
        "project_id": "inbox",
        "priority": 3,
        "labels": ["chainlbl"],
        "due": {"date": "2026-11-01", "string": "Nov 1"},
    }, headers=H).json()
    sid = src["id"]
    full = c.get(f"/api/v1/tasks/{sid}", headers=H).json()
    # duplicate-without-comments: client copies fields via item_add
    args = {
        "content": full["content"],
        "description": full.get("description", ""),
        "project_id": full.get("project_id", "inbox"),
        "priority": full.get("priority", 1),
        "labels": full.get("labels", []),
    }
    if "due" in full:
        args["due"] = {"date": full["due"].get("date"), "string": full["due"].get("string", ""),
                       "timezone": full["due"].get("timezone"), "lang": full["due"].get("lang", "en"),
                       "is_recurring": full["due"].get("is_recurring", False)}
    if "deadline" in full:
        args["deadline"] = {"date": full["deadline"]["date"]}
    if "duration" in full:
        args["duration"] = full["duration"]
    r = _sync(c, "*", [{"type": "item_add", "temp_id": "dup-chain-1", "uuid": "dup-c1", "args": args}])
    assert r.json()["sync_status"]["dup-c1"] == "ok", r.text
    nid = r.json()["temp_id_mapping"]["dup-chain-1"]
    assert nid != sid
    got = c.get(f"/api/v1/tasks/{nid}", headers=H).json()
    assert got["content"] == "chain src"
    assert got["description"] == "chain desc"
