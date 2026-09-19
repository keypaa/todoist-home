# tests/test_sync_write.py
import json
import os
os.environ["OPENDOIST_DB"] = ":memory:"
from fastapi.testclient import TestClient
from app.main import app
H = {"Authorization": "Bearer x"}


def _post(c, token, cmds):
    return c.post(
        "/api/v1/sync",
        data={
            "sync_token": token,
            "resource_types": '["all"]',
            "commands": json.dumps(cmds),
        },
        headers=H,
    )


def test_item_add_update_close():
    c = TestClient(app)
    cmds = [{"type": "item_add", "temp_id": "u1", "uuid": "a1", "args": {"content": "Write me", "project_id": "inbox"}}]
    r = _post(c, "*", cmds)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["sync_status"]["a1"] == "ok"
    assert "u1" in j["temp_id_mapping"]
    tid = j["temp_id_mapping"]["u1"]
    # uuid retry idempotent
    r2 = _post(c, j["sync_token"], cmds)
    assert r2.json()["sync_status"]["a1"] == "ok"
    # update + close
    cmds2 = [{"type": "item_update", "uuid": "a2", "args": {"id": tid, "content": "Renamed"}}, {"type": "item_close", "uuid": "a3", "args": {"id": tid}}]
    r3 = _post(c, r2.json()["sync_token"], cmds2)
    assert r3.json()["sync_status"]["a2"] == "ok"


def test_partial_update_preserves_due():
    c = TestClient(app)
    cmds = [{"type": "item_add", "temp_id": "t-due", "uuid": "due-1",
             "args": {"content": "Due task", "project_id": "inbox",
                      "due": {"date": "2026-10-01", "timezone": "Europe/Berlin", "string": "Oct 1"}}}]
    r = _post(c, "*", cmds)
    assert r.status_code == 200, r.text
    tid = r.json()["temp_id_mapping"]["t-due"]
    # partial update: only content -> due timezone/string preserved
    r2 = _post(c, r.json()["sync_token"],
               [{"type": "item_update", "uuid": "due-2", "args": {"id": tid, "content": "Due renamed"}}])
    assert r2.json()["sync_status"]["due-2"] == "ok"
    items = {i["id"]: i for i in r2.json()["items"] if "content" in i}
    assert items[tid]["content"] == "Due renamed"
    assert items[tid]["due"]["timezone"] == "Europe/Berlin"
    assert items[tid]["due"]["string"] == "Oct 1"


def test_parent_temp_id_remap_and_move_delete():
    c = TestClient(app)
    cmds = [
        {"type": "item_add", "temp_id": "t-parent", "uuid": "p-1",
         "args": {"content": "Parent", "project_id": "inbox"}},
        {"type": "item_add", "temp_id": "t-child", "uuid": "p-2",
         "args": {"content": "Child", "project_id": "inbox", "parent_id": "t-parent"}},
    ]
    r = _post(c, "*", cmds)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["sync_status"]["p-1"] == "ok" and j["sync_status"]["p-2"] == "ok"
    pid, cid = j["temp_id_mapping"]["t-parent"], j["temp_id_mapping"]["t-child"]
    items = {i["id"]: i for i in j["items"] if "content" in i}
    assert items[cid]["parent_id"] == pid
    # move child to no parent + delete parent
    r2 = _post(c, j["sync_token"], [
        {"type": "item_move", "uuid": "p-3", "args": {"id": cid, "parent_id": None}},
        {"type": "item_delete", "uuid": "p-4", "args": {"id": pid}},
    ])
    assert r2.json()["sync_status"]["p-3"] == "ok"
    assert r2.json()["sync_status"]["p-4"] == "ok"


def test_day_orders_and_reminder_and_close_hides_children():
    c = TestClient(app)
    r = _post(c, "*", [
        {"type": "item_add", "temp_id": "t-o1", "uuid": "o-1",
         "args": {"content": "O1", "project_id": "inbox"}},
        {"type": "item_add", "temp_id": "t-o2", "uuid": "o-2",
         "args": {"content": "O2", "project_id": "inbox"}},
    ])
    j = r.json()
    id1, id2 = j["temp_id_mapping"]["t-o1"], j["temp_id_mapping"]["t-o2"]
    r2 = _post(c, j["sync_token"], [
        {"type": "item_update_day_orders", "uuid": "o-3",
         "args": {"ids_to_orders": {id1: 3, id2: 1}}},
        {"type": "reminder_add", "uuid": "o-4",
         "args": {"item_id": id1, "minute_offset": 30}},
        {"type": "item_close", "uuid": "o-5", "args": {"id": id1}},
    ])
    j2 = r2.json()
    assert j2["sync_status"]["o-3"] == "ok", j2
    assert j2["sync_status"]["o-4"] == "ok", j2
    assert j2["sync_status"]["o-5"] == "ok", j2
    assert j2["day_orders"].get(id2) == 1
