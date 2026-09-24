"""Quick-add parser for OpenDoist V1 (Phase 4 Task 4) — auto-detect FR/EN + lang override."""
import datetime

from app import nlp
import app.nlp.en  # noqa: F401 — ensure EN module registered in nlp.LANGUAGES
import app.nlp.fr  # noqa: F401 — ensure FR module registered in nlp.LANGUAGES
from app.nlp.base import extract_tokens


def parse_quick_add(text, today_iso, lang="auto"):
    assignee, reminder, deadline = None, None, None

    t = text

    # Explicit override wins when it names a registered language;
    # anything else ("auto", unknown, None) falls back to detection.
    code = lang if lang in nlp.LANGUAGES else nlp.detect(text)
    mod = nlp.LANGUAGES.get(code)
    base = datetime.date.fromisoformat(today_iso)
    if mod is not None and hasattr(mod, "find_dates"):
        found = mod.find_dates(t, base)
    else:
        found = {"due_date": None, "due_datetime": None, "spans": []}
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
        "lang": code,
    }
