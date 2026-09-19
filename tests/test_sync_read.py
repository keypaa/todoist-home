# tests/test_sync_read.py
import os
os.environ["OPENDOIST_DB"] = ":memory:"
from fastapi.testclient import TestClient
from app.main import app
H = {"Authorization": "Bearer x"}
def test_sync_star_returns_user_and_items():
    c = TestClient(app)
    r = c.post("/api/v1/sync", data={"sync_token": "*", "resource_types": '["items","projects","sections","labels","user","collaborators","reminders","completed_info"]'}, headers=H)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "user" in j and j["user"]["id"] == "1"
    assert "items" in j and "day_orders" in j and "sync_token" in j
def test_sync_user_only_validates_token():
    c = TestClient(app)
    r = c.post("/api/v1/sync", data={"sync_token": "*", "resource_types": '["user"]'}, headers=H)
    assert r.status_code == 200 and "user" in r.json()
