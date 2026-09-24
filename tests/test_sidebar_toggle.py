# tests/test_sidebar_toggle.py
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app


def test_index_has_sidebar_toggle_control():
    c = TestClient(app)
    r = c.get("/")
    assert r.status_code == 200
    assert 'id="sidebar-toggle"' in r.text


def test_app_js_wires_sidebar_toggle_with_collapse_logic():
    js = Path(__file__).resolve().parent.parent / "app" / "web" / "app.js"
    text = js.read_text()
    assert "sidebar-toggle" in text
    assert "sidebar-collapsed" in text
