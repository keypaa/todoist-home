# tests/test_api_mutations.py
import os
os.environ["OPENDOIST_DB"] = ":memory:"
import datetime
from fastapi.testclient import TestClient
from app.main import app

H = {"Authorization": "Bearer x"}


def test_partial_update_preserves_due_string():
    c = TestClient(app)
    r = c.post("/api/v1/tasks/quick", json={"text": "Meet tomorrow"}, headers=H)
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    orig = c.get(f"/api/v1/tasks/{tid}", headers=H).json()
    assert orig.get("due", {}).get("date"), orig
    u = c.post(f"/api/v1/tasks/{tid}", json={"content": "Meet renamed"}, headers=H)
    assert u.status_code == 200, u.text
    after = c.get(f"/api/v1/tasks/{tid}", headers=H).json()
    assert "renamed" in after["content"].lower(), after
    assert after.get("due", {}).get("date") == orig.get("due", {}).get("date"), (orig, after)
    # title-only must preserve string/tz/recurrence when present
    assert after.get("due", {}).get("string") == orig.get("due", {}).get("string"), (orig, after)


def test_deadline_validation():
    c = TestClient(app)
    tid = c.post("/api/v1/tasks", json={"content": "t"}, headers=H).json()["id"]
    r = c.post(f"/api/v1/tasks/{tid}", json={"deadline_date": "never"}, headers=H)
    assert r.status_code == 400, r.text
    # valid forms accepted
    for val in ("Today", "Tomorrow", "Next week", str(datetime.date.today())):
        tid2 = c.post("/api/v1/tasks", json={"content": "t2"}, headers=H).json()["id"]
        ok = c.post(f"/api/v1/tasks/{tid2}", json={"deadline_date": val}, headers=H)
        assert ok.status_code == 200, (val, ok.text)


def test_delete_sets_deleted():
    c = TestClient(app)
    tid = c.post("/api/v1/tasks", json={"content": "to delete"}, headers=H).json()["id"]
    d = c.delete(f"/api/v1/tasks/{tid}", headers=H)
    assert d.status_code in (200, 204), d.text
    g = c.get(f"/api/v1/tasks/{tid}", headers=H)
    assert g.status_code == 404, g.text
    lst = c.get("/api/v1/tasks", headers=H).json()["results"]
    assert all(t["id"] != tid for t in lst)


def test_close_hides_children_no_recurrence():
    c = TestClient(app)
    pid = c.post("/api/v1/tasks", json={"content": "P"}, headers=H).json()["id"]
    cid = c.post("/api/v1/tasks", json={"content": "C", "parent_id": pid}, headers=H).json()["id"]
    before = c.get("/api/v1/tasks", headers=H).json()["results"]
    n_before = len(before)
    r = c.post(f"/api/v1/tasks/{pid}/close", headers=H)
    assert r.status_code in (200, 204), r.text
    after = c.get("/api/v1/tasks", headers=H).json()["results"]
    ids = {t["id"] for t in after}
    assert pid not in ids and cid not in ids, after
    # no fake recurrence: no new tasks created
    assert len(after) == n_before - 2, (n_before, after)


def test_reopen_clears():
    c = TestClient(app)
    tid = c.post("/api/v1/tasks", json={"content": "R"}, headers=H).json()["id"]
    c.post(f"/api/v1/tasks/{tid}/close", headers=H)
    r = c.post(f"/api/v1/tasks/{tid}/reopen", headers=H)
    assert r.status_code in (200, 204), r.text
    lst = c.get("/api/v1/tasks", headers=H).json()["results"]
    assert any(t["id"] == tid for t in lst), lst


def test_move_project_section():
    c = TestClient(app)
    tid = c.post("/api/v1/tasks", json={"content": "M"}, headers=H).json()["id"]
    r = c.post(f"/api/v1/tasks/{tid}/move", json={"project_id": "inbox"}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json().get("project_id") == "inbox", r.text
    # move with section_id key present (None clears / sets)
    r2 = c.post(f"/api/v1/tasks/{tid}/move", json={"project_id": "inbox", "section_id": None}, headers=H)
    assert r2.status_code == 200, r2.text


def test_update_404():
    c = TestClient(app)
    r = c.post("/api/v1/tasks/nope-missing-id", json={"content": "x"}, headers=H)
    assert r.status_code == 404, r.text
