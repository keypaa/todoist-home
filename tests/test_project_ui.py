# tests/test_project_ui.py — fix B: full Add-project modal + project menu (frontend only)
from fastapi.testclient import TestClient
from app.main import app


def _index_text():
    c = TestClient(app)
    r = c.get("/")
    assert r.status_code == 200
    return r.text


def _app_js():
    c = TestClient(app)
    r = c.get("/static/app.js")
    assert r.status_code == 200
    return r.text


def test_modal_has_all_fields():
    html = _index_text()
    # modal container + title
    assert "project-modal" in html
    assert "Add project" in html
    # Name input + 0/120 counter
    assert "project-input" in html
    assert "0/120" in html
    # Description textarea
    assert "project-desc" in html
    assert "<textarea" in html
    # Color select with Charcoal default + Todoist colors
    assert "project-color" in html
    assert "Charcoal" in html
    for color in ("Berry Red", "Red", "Charcoal", "Blue", "Green"):
        assert color in html, f"missing color {color}"
    # Workspace select (My Projects)
    assert "project-workspace" in html
    assert "My Projects" in html
    # Parent project select (No Parent + populated via JS)
    assert "project-parent" in html
    assert "No Parent" in html
    # Access select (Restricted)
    assert "project-access" in html
    assert "Restricted" in html
    # Add-to-favorites toggle
    assert "project-fav" in html
    assert "favorites" in html.lower()
    # Layout List/Board/Calendar picker
    assert "project-layout" in html or "data-layout" in html
    assert "List" in html and "Board" in html and "Calendar" in html
    # Cancel/Add buttons
    assert "project-cancel" in html
    assert "project-submit" in html


def test_project_rows_have_menu_button():
    html = _index_text()
    js = _app_js()
    # static shell has project list container
    assert "project-list" in html
    # rows render a ⋯ menu button (JS-rendered): assert JS builds it
    assert "⋯" in js or "proj-menu" in js
    assert "proj-menu-btn" in js or "proj-menu" in html or "proj-menu" in js
    # dropdown menu items wired in JS
    for item in ("above", "below", "Edit", "Archive", "Delete", "favorite", "Copy link", "coming in complete app"):
        assert item in js, f"missing menu handler: {item}"
    # modal submit posts all fields; counter live; diagnosable error toasts
    for token in ("description", "is_favorite", "layout", "parent_id", "workspace", "access", "color"):
        assert token in js, f"missing field passthrough: {token}"
    assert "120" in js
    assert "Projects load failed" in js
