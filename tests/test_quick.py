# tests/test_quick.py
import os
os.environ["OPENDOIST_DB"] = ":memory:"
import datetime
from fastapi.testclient import TestClient
from app.main import app

H = {"Authorization": "Bearer test123"}


def _today():
    return datetime.date.today()


def _next_monday(base):
    d = base
    while True:
        d += datetime.timedelta(days=1)
        if d.weekday() == 0:
            break
    return d


def test_quick_tokens_autocreate():
    c = TestClient(app)
    r = c.post("/api/v1/tasks/quick", json={"text": "Buy milk tomorrow #Shopping @errands p1"}, headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["content"] == "Buy milk"
    assert body["priority"] == 4
    assert "errands" in body["labels"]
    assert body["due"]["date"] == str(_today() + datetime.timedelta(days=1))
    assert body["project_id"] != "inbox"


def test_quick_bare_defaults_today():
    c = TestClient(app)
    r = c.post("/api/v1/tasks/quick", json={"text": "Quick bare task"}, headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["content"] == "Quick bare task"
    assert body["due"]["date"] == str(_today())


def test_quick_idempotency():
    c = TestClient(app)
    headers = dict(H)
    headers["X-Request-Id"] = "req-123-unique"
    r1 = c.post("/api/v1/tasks/quick", json={"text": "Idempotent task"}, headers=headers)
    r2 = c.post("/api/v1/tasks/quick", json={"text": "Idempotent task"}, headers=headers)
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    assert r1.json()["id"] == r2.json()["id"]


def test_quick_auto_reminder_ignored():
    c = TestClient(app)
    r = c.post("/api/v1/tasks/quick", json={"text": "Reminder task", "auto_reminder": {"minute_offset": 30}}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["content"] == "Reminder task"


def test_quick_quoted_project_section_next_monday():
    c = TestClient(app)
    r = c.post(
        "/api/v1/tasks/quick",
        json={"text": 'Plan party #"My Project" /Logistics next Monday p2'},
        headers=H,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["content"] == "Plan party"
    assert body["priority"] == 3
    assert body["due"]["date"] == str(_next_monday(_today()))
    # section resolved
    assert body["section_id"] is not None


def test_quick_datetime_persisted_end_to_end():
    c = TestClient(app)
    r = c.post("/api/v1/tasks/quick", json={"text": "Call mom tomorrow at 5pm"}, headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    exp_date = str(_today() + datetime.timedelta(days=1))
    assert body["due"]["date"] == exp_date
    assert body["due"].get("datetime") == f"{exp_date}T17:00"
    g = c.get(f"/api/v1/tasks/{body['id']}", headers=H)
    assert g.status_code == 200, g.text
    assert g.json()["due"].get("datetime") == f"{exp_date}T17:00"


def test_quick_datetime_french_persisted():
    c = TestClient(app)
    r = c.post("/api/v1/tasks/quick", json={"text": "Réunion lundi 10h"}, headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    exp = str(_next_monday(_today()))
    assert body["due"]["date"] == exp
    assert body["due"].get("datetime") == f"{exp}T10:00"
    assert body["due"].get("lang") == "fr"
