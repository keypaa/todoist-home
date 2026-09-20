# tests/test_project_fields.py
import os
os.environ["OPENDOIST_DB"] = ":memory:"
from fastapi.testclient import TestClient
from app.main import app

H = {"Authorization": "Bearer x"}

FULL = {
    "name": "FieldProj",
    "description": "my desc",
    "color": "red",
    "workspace": "Team",
    "parent_id": None,
    "access": "Shared",
    "is_favorite": True,
    "layout": "board",
}


def test_create_returns_all_fields():
    c = TestClient(app)
    r = c.post("/api/v1/projects", json=FULL, headers=H)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["name"] == "FieldProj"
    assert data["description"] == "my desc"
    assert data["color"] == "red"
    assert data["workspace"] == "Team"
    assert data.get("parent_id") is None
    assert data["access"] == "Shared"
    assert data["is_favorite"] is True
    assert data["layout"] == "board"


def test_get_returns_same():
    c = TestClient(app)
    pid = c.post("/api/v1/projects", json=FULL, headers=H).json()["id"]
    g = c.get(f"/api/v1/projects/{pid}", headers=H)
    assert g.status_code == 200, g.text
    data = g.json()
    assert data["description"] == "my desc"
    assert data["color"] == "red"
    assert data["workspace"] == "Team"
    assert data["access"] == "Shared"
    assert data["is_favorite"] is True
    assert data["layout"] == "board"


def test_update_persists_fields():
    c = TestClient(app)
    pid = c.post("/api/v1/projects", json={"name": "Upd0"}, headers=H).json()["id"]
    u = c.post(f"/api/v1/projects/{pid}", json={
        "description": "updated desc",
        "color": "blue",
        "workspace": "Ws2",
        "access": "Restricted",
        "is_favorite": True,
        "layout": "calendar",
    }, headers=H)
    assert u.status_code == 200, u.text
    data = u.json()
    assert data["description"] == "updated desc"
    assert data["color"] == "blue"
    assert data["workspace"] == "Ws2"
    assert data["is_favorite"] is True
    assert data["layout"] == "calendar"
    g = c.get(f"/api/v1/projects/{pid}", headers=H).json()
    assert g["description"] == "updated desc"
    assert g["color"] == "blue"
    assert g["layout"] == "calendar"


def test_defaults():
    c = TestClient(app)
    pid = c.post("/api/v1/projects", json={"name": "DefProj"}, headers=H).json()["id"]
    data = c.get(f"/api/v1/projects/{pid}", headers=H).json()
    assert data["description"] == ""
    assert data["color"] == "charcoal"
    assert data["workspace"] == "My Projects"
    assert data.get("parent_id") is None
    assert data["access"] == "Restricted"
    assert data["is_favorite"] is False
    assert data["layout"] == "list"


def test_name_required():
    c = TestClient(app)
    r = c.post("/api/v1/projects", json={"name": ""}, headers=H)
    assert r.status_code == 400, r.text
    r2 = c.post("/api/v1/projects", json={}, headers=H)
    assert r2.status_code == 400, r2.text
    pid = c.post("/api/v1/projects", json={"name": "N1"}, headers=H).json()["id"]
    u = c.post(f"/api/v1/projects/{pid}", json={"name": "  "}, headers=H)
    assert u.status_code == 400, u.text


def test_color_allowlist():
    c = TestClient(app)
    r = c.post("/api/v1/projects", json={"name": "C1", "color": "not-a-color"}, headers=H)
    assert r.status_code == 400, r.text
    pid = c.post("/api/v1/projects", json={"name": "C2"}, headers=H).json()["id"]
    u = c.post(f"/api/v1/projects/{pid}", json={"color": "bogus"}, headers=H)
    assert u.status_code == 400, u.text


def test_layout_validation():
    c = TestClient(app)
    r = c.post("/api/v1/projects", json={"name": "L1", "layout": "kanban"}, headers=H)
    assert r.status_code == 400, r.text
    pid = c.post("/api/v1/projects", json={"name": "L2"}, headers=H).json()["id"]
    u = c.post(f"/api/v1/projects/{pid}", json={"layout": "timeline"}, headers=H)
    assert u.status_code == 400, u.text
    for layout in ("list", "board", "calendar"):
        pid2 = c.post("/api/v1/projects", json={"name": f"L-{layout}", "layout": layout}, headers=H)
        assert pid2.status_code == 200, (layout, pid2.text)
        assert pid2.json()["layout"] == layout


def test_sync_includes_fields():
    c = TestClient(app)
    pid = c.post("/api/v1/projects", json=FULL, headers=H).json()["id"]
    r = c.post("/api/v1/sync", data={"sync_token": "*", "resource_types": '["projects"]'}, headers=H)
    assert r.status_code == 200, r.text
    projs = {p["id"]: p for p in r.json().get("projects", [])}
    assert pid in projs, projs.keys()
    assert projs[pid]["color"] == "red"
    assert projs[pid]["layout"] == "board"
