# tests/test_api_tasks.py
import os
os.environ["OPENDOIST_DB"] = ":memory:"
from fastapi.testclient import TestClient
from app.main import app
H = {"Authorization": "Bearer test123"}
def test_create_and_get_task():
    c = TestClient(app)
    r = c.post("/api/v1/tasks", json={"content": "Buy milk", "project_id": "inbox"}, headers=H)
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    g = c.get(f"/api/v1/tasks/{tid}", headers=H)
    assert g.status_code == 200
    assert g.json()["content"] == "Buy milk"
def test_no_token_401():
    c = TestClient(app)
    r = c.get("/api/v1/tasks", headers={})
    assert r.status_code == 401
    assert r.json()["error_code"] == 477
def test_tmp_id_rejected():
    c = TestClient(app)
    r = c.get("/api/v1/tasks/tmp-abc-123", headers=H)
    assert r.status_code == 400
