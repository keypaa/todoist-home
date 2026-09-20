# tests/test_delete_modal.py
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

WEB_DIR = Path(__file__).resolve().parent.parent / "app" / "web"


def _index_html():
    c = TestClient(app)
    r = c.get("/")
    assert r.status_code == 200
    return r.text


def _app_js():
    c = TestClient(app)
    r = c.get("/static/app.js")
    assert r.status_code == 200
    return r.text


def test_index_has_delete_confirm_modal():
    html = _index_html()
    assert 'id="delete-modal"' in html
    assert 'id="delete-modal-title"' in html
    assert 'id="delete-modal-body"' in html
    assert 'id="delete-cancel"' in html
    assert 'id="delete-confirm"' in html


def test_delete_modal_uses_existing_styles():
    html = _index_html()
    # modal reuses existing .modal / .modal-card / .btn styles
    assert "modal-card" in html
    assert "modal-actions" in html or "btn" in html


def test_app_js_has_no_native_confirm():
    js = _app_js()
    assert "confirm(" not in js
