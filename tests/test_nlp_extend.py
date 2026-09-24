# tests/test_nlp_extend.py
def test_third_language_plugs_in():
    from app import nlp
    import datetime
    class XX:
        @staticmethod
        def find_dates(text, today): return {"due_date": "2030-01-01", "due_datetime": None, "spans": []}
    nlp.register("xx-test", XX)
    assert "xx-test" in nlp.LANGUAGES
    from app.parser import parse_quick_add
    assert parse_quick_add("whatever", "2026-09-19", lang="xx-test")["due_date"] == "2030-01-01"
    del nlp.LANGUAGES["xx-test"]
