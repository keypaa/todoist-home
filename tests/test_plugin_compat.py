# tests/test_plugin_compat.py — omatasks compat gate (Task 10, V1-T3).
import os
os.environ["OPENDOIST_DB"] = ":memory:"
import json
from fastapi.testclient import TestClient
from app.main import app
H = {"Authorization": "Bearer local-dev"}
def test_omatasks_sequence():
    c = TestClient(app)
    assert c.post("/api/v1/sync", data={"sync_token": "*", "resource_types": '["user"]'}, headers=H).status_code == 200
    t = c.post("/api/v1/tasks/quick", json={"text": "Demo tomorrow #Work p2", "auto_reminder": True}, headers={**H, "X-Request-Id": "q1"}).json()
    assert t["content"].startswith("Demo")
    assert c.post("/api/v1/sync", data={"sync_token": "*", "resource_types": '["items","projects","sections","labels","user","collaborators","reminders","completed_info"]'}, headers=H).status_code == 200
    assert c.post(f"/api/v1/tasks/{t['id']}/close", headers=H).status_code in (200, 204)
