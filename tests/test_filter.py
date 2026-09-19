# tests/test_filter.py
import os
os.environ["OPENDOIST_DB"] = ":memory:"
from fastapi.testclient import TestClient
from app.main import app
H = {"Authorization": "Bearer x"}
def test_filter_today_overdue():
    c = TestClient(app)
    c.post("/api/v1/tasks/quick", json={"text": "Overdue thing yesterday"}, headers=H)
    r = c.get("/api/v1/tasks/filter", params={"query": "today | overdue"}, headers=H)
    assert r.status_code == 200 and "results" in r.json()
