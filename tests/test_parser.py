# tests/test_parser.py
from app.parser import parse_quick_add
def test_tokens():
    p = parse_quick_add("Buy milk tomorrow #Shopping @errands p1", "2026-09-19")
    assert p["content"] == "Buy milk"
    assert p["project"] == "Shopping"
    assert "errands" in p["labels"]
    assert p["priority"] == 4
    assert p["due_date"] == "2026-09-20"
def test_bare_defaults_handled_by_server():
    p = parse_quick_add("Buy milk", "2026-09-19")
    assert p["content"] == "Buy milk"
    assert p["due_date"] is None
def test_escaped_and_percent():
    p = parse_quick_add(r"Fix \#bug %home", "2026-09-19")
    assert "#" not in p["content"] or "\\#" not in p["content"]
    assert "home" in p["labels"]
