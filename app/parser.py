"""EN quick-add parser for OpenDoist V1 (Task 3) — thin wrapper over app.nlp."""
import re
import datetime

from app import nlp
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

    tok = extract_tokens(t)
    project, labels, section, priority = tok["project"], tok["labels"], tok["section"], tok["priority"]
    spans = list(tok["spans"])

    # Registry lookup (no behavior change yet: EN fallback when unregistered)
    lang = nlp.detect(text)
    mod = nlp.LANGUAGES.get(lang)
    base = datetime.date.fromisoformat(today_iso)
    if mod is not None and hasattr(mod, "find_dates"):
        found = mod.find_dates(t, base)
        due_date, due_dt = found["due_date"], found["due_datetime"]
        spans.extend(found["spans"])
    else:
        found = find_dates(t, base)
        due_date, due_dt = found["due_date"], found["due_datetime"]
        spans.extend(found["spans"])

    # Remove token spans from content (reverse order to keep offsets valid)
    content_parts = t
    # Apply removals by replacing spans with spaces
    # Sort spans by start descending
    chars = list(t)
    for s, e in sorted(spans, key=lambda x: x[0], reverse=True):
        for i in range(s, e):
            chars[i] = " "
    content_parts = "".join(chars)
    content_parts = re.sub(r"\s+", " ", content_parts).strip()
    content_parts = (
        content_parts.replace("\\#", "#").replace("\\@", "@").replace("\\%", "%").replace("\\/", "/")
    )
    content = content_parts or text.strip()

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
