# tests/test_nlp_parity.py
from app.parser import parse_quick_add
def test_auto_and_override():
    assert parse_quick_add("Acheter du pain demain", "2026-09-19")["due_date"] == "2026-09-20"
    assert parse_quick_add("Buy milk tomorrow", "2026-09-19")["due_date"] == "2026-09-20"
    assert parse_quick_add("Buy milk tomorrow", "2026-09-19", lang="fr")["due_date"] is None  # forced FR ignores EN date
    assert parse_quick_add("Réunion lundi 10h", "2026-09-19")["due_datetime"] == "2026-09-21T10:00"
    assert parse_quick_add("Monday 10am meeting in Paris", "2026-09-19")["due_datetime"] == "2026-09-21T10:00"
def test_tokens_still_work_in_french():
    p = parse_quick_add("Acheter du lait demain #Courses @maison p1", "2026-09-19")
    assert p["content"] == "Acheter du lait" and p["project"] == "Courses" and p["priority"] == 4
