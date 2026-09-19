"""EN quick-add parser for OpenDoist V1 (Task 3)."""
import re
import datetime

DATES = {"today": 0, "tomorrow": 1, "next week": 7}


def _strip_trailing_punct(name: str) -> str:
    return name.rstrip(",.;:!?)")


def parse_quick_add(text, today_iso):
    labels, project, section, priority = [], None, None, 1
    assignee, reminder, deadline = None, None, None

    t = text

    spans = []

    m = re.search(r"\bp([1-4])\b", t)
    if m:
        priority = 5 - int(m.group(1))
        spans.append(m.span())

    # #project incl quoted ("..." or '...')
    for mm in re.finditer(r'(?<!\\)#(?:"([^"]+)"|\'([^\']+)\'|(\S+))', t):
        name = mm.group(1) or mm.group(2) or mm.group(3)
        project = _strip_trailing_punct(name)
        spans.append(mm.span())

    # @ / % labels
    for mm in re.finditer(r'(?<!\\)[@%](\S+)', t):
        labels.append(_strip_trailing_punct(mm.group(1)))
        spans.append(mm.span())

    # /section (require token start at whitespace or string start to avoid URLs)
    for mm in re.finditer(r'(?<!\\)(?:(?<=\s)|^)/(\S+)', t):
        section = _strip_trailing_punct(mm.group(1))
        spans.append(mm.span())

    # EN dates (case-insensitive, word boundaries)
    low = text.lower()
    due_date, due_dt = None, None
    base = datetime.date.fromisoformat(today_iso)
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
    spans.extend(date_spans)

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
