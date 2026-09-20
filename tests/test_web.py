# tests/test_web.py
from fastapi.testclient import TestClient
from app.main import app
def test_index_has_sidebar_and_today():
    c = TestClient(app)
    r = c.get("/")
    assert r.status_code == 200
    assert "Today" in r.text and "Inbox" in r.text
    assert "#E44332" in r.text or "E44332" in r.text
