# tests/test_meta_tz.py
import os
os.environ["OPENDOIST_DB"] = ":memory:"
from fastapi.testclient import TestClient
from app.main import app

H = {"Authorization": "Bearer x"}


def test_project_crud_and_tz_preserve():
    c = TestClient(app)
    p = c.post("/api/v1/projects", json={"name": "Work"}, headers=H)
    assert p.status_code == 200, p.text
    pid = p.json()["id"]
    assert c.get("/api/v1/projects", headers=H).status_code == 200
    assert c.post("/api/v1/sections", json={"project_id": pid, "name": "S1"}, headers=H).status_code == 200
    assert c.post("/api/v1/labels", json={"name": "home"}, headers=H).status_code == 200


def test_project_full_crud_archive():
    c = TestClient(app)
    p = c.post("/api/v1/projects", json={"name": "ProjFull"}, headers=H)
    assert p.status_code == 200, p.text
    pid = p.json()["id"]
    assert p.json()["name"] == "ProjFull"
    # get
    g = c.get(f"/api/v1/projects/{pid}", headers=H)
    assert g.status_code == 200, g.text
    assert g.json()["id"] == pid
    # list contains
    lst = c.get("/api/v1/projects", headers=H).json()
    items = lst if isinstance(lst, list) else lst.get("results", lst)
    if isinstance(items, dict):
        items = list(items.values())
    assert any(x.get("id") == pid for x in items), lst
    # update
    u = c.post(f"/api/v1/projects/{pid}", json={"name": "ProjRenamed"}, headers=H)
    assert u.status_code == 200, u.text
    assert u.json()["name"] == "ProjRenamed"
    # archive / unarchive flags
    a = c.post(f"/api/v1/projects/{pid}/archive", headers=H)
    assert a.status_code == 200, a.text
    assert a.json()["is_archived"] is True
    ua = c.post(f"/api/v1/projects/{pid}/unarchive", headers=H)
    assert ua.status_code == 200, ua.text
    assert ua.json()["is_archived"] is False
    # delete -> get 404
    d = c.delete(f"/api/v1/projects/{pid}", headers=H)
    assert d.status_code in (200, 204), d.text
    assert c.get(f"/api/v1/projects/{pid}", headers=H).status_code == 404


def test_section_crud_and_archive_flag():
    c = TestClient(app)
    pid = c.post("/api/v1/projects", json={"name": "SecProj"}, headers=H).json()["id"]
    s = c.post("/api/v1/sections", json={"project_id": pid, "name": "S1full"}, headers=H)
    assert s.status_code == 200, s.text
    sid = s.json()["id"]
    assert s.json()["project_id"] == pid
    g = c.get(f"/api/v1/sections/{sid}", headers=H)
    assert g.status_code == 200, g.text
    u = c.post(f"/api/v1/sections/{sid}", json={"name": "S1renamed"}, headers=H)
    assert u.status_code == 200, u.text
    assert u.json()["name"] == "S1renamed"
    a = c.post(f"/api/v1/sections/{sid}/archive", headers=H)
    assert a.status_code == 200, a.text
    assert a.json()["is_archived"] is True
    ua = c.post(f"/api/v1/sections/{sid}/unarchive", headers=H)
    assert ua.status_code == 200, ua.text
    assert ua.json()["is_archived"] is False
    # list (optionally filtered by project)
    lst = c.get("/api/v1/sections", params={"project_id": pid}, headers=H)
    assert lst.status_code == 200, lst.text
    d = c.delete(f"/api/v1/sections/{sid}", headers=H)
    assert d.status_code in (200, 204), d.text
    assert c.get(f"/api/v1/sections/{sid}", headers=H).status_code == 404


def test_label_crud():
    c = TestClient(app)
    lb = c.post("/api/v1/labels", json={"name": "homefull"}, headers=H)
    assert lb.status_code == 200, lb.text
    lid = lb.json()["id"]
    g = c.get(f"/api/v1/labels/{lid}", headers=H)
    assert g.status_code == 200, g.text
    assert g.json()["name"] == "homefull"
    lst = c.get("/api/v1/labels", headers=H)
    assert lst.status_code == 200, lst.text
    u = c.post(f"/api/v1/labels/{lid}", json={"name": "homerenamed"}, headers=H)
    assert u.status_code == 200, u.text
    assert u.json()["name"] == "homerenamed"
    d = c.delete(f"/api/v1/labels/{lid}", headers=H)
    assert d.status_code in (200, 204), d.text
    assert c.get(f"/api/v1/labels/{lid}", headers=H).status_code == 404


def test_task_due_timezone_preserved_on_partial_update():
    c = TestClient(app)
    r = c.post("/api/v1/tasks", json={
        "content": "tz task",
        "due": {"date": "2026-09-19", "datetime": "2026-09-19T15:00:00Z",
                "timezone": "America/New_York", "string": "today 11am"},
    }, headers=H)
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    got = c.get(f"/api/v1/tasks/{tid}", headers=H).json()
    assert got["due"]["timezone"] == "America/New_York", got
    # title-only update preserves timezone/string
    u = c.post(f"/api/v1/tasks/{tid}", json={"content": "tz task renamed"}, headers=H)
    assert u.status_code == 200, u.text
    after = c.get(f"/api/v1/tasks/{tid}", headers=H).json()
    assert after["due"]["timezone"] == "America/New_York", after
    assert after["due"]["string"] == "today 11am", after
    # partial due date update without datetime preserves timezone
    u2 = c.post(f"/api/v1/tasks/{tid}", json={"due": {"date": "2026-09-20"}}, headers=H)
    assert u2.status_code == 200, u2.text
    after2 = c.get(f"/api/v1/tasks/{tid}", headers=H).json()
    assert after2["due"]["timezone"] == "America/New_York", after2
    assert after2["due"]["date"] == "2026-09-20", after2


def test_filter_today_overdue_tz_aware():
    c = TestClient(app)
    # Task due today *in its own timezone* must show up in today filter.
    import datetime
    from zoneinfo import ZoneInfo
    tzname = "America/New_York"
    today = datetime.datetime.now(ZoneInfo(tzname)).date().isoformat()
    r = c.post("/api/v1/tasks", json={
        "content": "tz filter probe",
        "due": {"date": today, "timezone": tzname, "string": "today"},
    }, headers=H)
    assert r.status_code == 200, r.text
    f = c.get("/api/v1/tasks/filter", params={"query": "today"}, headers=H)
    assert f.status_code == 200, f.text
    ids = {t["id"] for t in f.json()["results"]}
    assert r.json()["id"] in ids, f.json()
    # overdue branch still works
    o = c.get("/api/v1/tasks/filter", params={"query": "today | overdue"}, headers=H)
    assert o.status_code == 200 and "results" in o.json()
