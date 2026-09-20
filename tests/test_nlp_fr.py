# tests/test_nlp_fr.py
import datetime
from app.nlp.fr import find_dates
T = datetime.date(2026, 9, 19)
def test_fr_parity():
    assert find_dates("Réunion demain", T)["due_date"] == "2026-09-20"
    assert find_dates("Courses aujourd'hui", T)["due_date"] == "2026-09-19"
    assert find_dates("Appel lundi", T)["due_date"] == "2026-09-21"
    assert find_dates("Dentiste lundi prochain", T)["due_date"] == "2026-09-28"
    assert find_dates("Facture dans 3 jours", T)["due_date"] == "2026-09-22"
    r = find_dates("Journée des associations mardi 22 septembre 13:00", T)
    assert r["due_date"] == "2026-09-22" and r["due_datetime"] == "2026-09-22T13:00"
    r2 = find_dates("Réunion demain à 17h", T)
    assert r2["due_datetime"] == "2026-09-20T17:00"
