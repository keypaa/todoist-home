"""EN quick-add parser for OpenDoist V1 (Task 3) — thin wrapper over app.nlp."""
import re
import datetime

from app import nlp
import app.nlp.en  # noqa: F401 — ensure EN module registered in nlp.LANGUAGES
from app.nlp.base import extract_tokens

DATES = {"today": 0, "tomorrow": 1, "next week": 7}


def _strip_trailing_punct(name: str) -> str:
    return name.rstrip(",.;:!?)")


def find_dates(text, today):
    # EN dates (case-insensitive, word boundaries)
    t = text
    low = text.lower()
    due_date, due_dt = None, None
    base = today
    date_spans = []
    for pat in (r"\bnext\s+monday\b", r"\btomorrow\b", r"\btoday\b", r"\bnext\s+week\b"):
        for mm in re.finditer(pat, t, flags=re.IGNORECASE):
            date_spans.append(mm.span())
    if "next monday" in low:
        d = base
        while True:
            d += datetime.timedelta(days=1)
            if d.weekday() == 0:
                break
        due_date = str(d)
    elif "tomorrow" in low:
        due_date = str(base + datetime.timedelta(days=1))
    elif "today" in low:
        due_date = str(base)
    elif "next week" in low:
        due_date = str(base + datetime.timedelta(days=7))
    return {"due_date": due_date, "due_datetime": due_dt, "spans": date_spans}


def parse_quick_add(text, today_iso):
    assignee, reminder, deadline = None, None, None

    t = text

    # Registry lookup (no behavior change yet: EN fallback when unregistered)
    lang = nlp.detect(text)
    mod = nlp.LANGUAGES.get(lang)
    base = datetime.date.fromisoformat(today_iso)
    if mod is not None and hasattr(mod, "find_dates"):
        found = mod.find_dates(t, base)
    else:
        found = find_dates(t, base)
    due_date, due_dt = found["due_date"], found["due_datetime"]

    tok = extract_tokens(t, extra_spans=found["spans"])
    project, labels, section, priority = tok["project"], tok["labels"], tok["section"], tok["priority"]
    content = tok["cleaned"] or text.strip()

    return {
        "content": content,
        "project": project,
        "labels": labels,
        "priority": priority,
        "section": section,
        "due_date": due_date,
        "due_datetime": due_dt,
        "assignee": assignee,
        "reminder": reminder,
        "deadline": deadline,
    }
