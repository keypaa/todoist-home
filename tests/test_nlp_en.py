# tests/test_nlp_en.py
import datetime
from app.nlp.en import find_dates
T = datetime.date(2026, 9, 19)  # a Saturday
def test_en_times():
    r = find_dates("Meeting tomorrow at 5pm", T)
    assert r["due_date"] == "2026-09-20" and r["due_datetime"] == "2026-09-20T17:00"
def test_en_weekday_and_relative():
    assert find_dates("Call Monday", T)["due_date"] == "2026-09-21"
    assert find_dates("Pay in 3 days", T)["due_date"] == "2026-09-22"
    assert find_dates("Dentist 2026-10-02", T)["due_date"] == "2026-10-02"
