"""EN date parsing for OpenDoist V1 (Phase 4 Task 2)."""
import re
import datetime

WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

# Longest-first alternation so 'thursday' wins over 'thu', etc.
_WDAY_ALT = r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|thurs|thur|tues|mon|tue|wed|thu|fri|sat|sun"

_ISO_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_TODAY_RE = re.compile(r"\btoday\b", re.IGNORECASE)
_TOMORROW_RE = re.compile(r"\btomorrow\b", re.IGNORECASE)
_NEXT_WEEK_RE = re.compile(r"\bnext\s+week\b", re.IGNORECASE)
_IN_N_RE = re.compile(r"\bin\s+(\d+)\s+(days?|weeks?)\b", re.IGNORECASE)
_NEXT_WDAY_RE = re.compile(r"\bnext\s+(%s)\b" % _WDAY_ALT, re.IGNORECASE)
_WDAY_RE = re.compile(r"\b(%s)\b" % _WDAY_ALT, re.IGNORECASE)

# Time attached immediately after a date match: optional 'at', then H(:MM)? + am/pm?
# Requires at least one of: 'at' prefix, ':MM' suffix, or am/pm suffix (to avoid bare numbers).
_TIME_RE = re.compile(
    r"^(\s+(?:at\s+)?)(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?\b",
    re.IGNORECASE,
)


def _parse_time(hour_s, min_s, ampm_s, has_at, has_colon):
    has_ampm = bool(ampm_s)
    if not (has_at or has_colon or has_ampm):
        return None
    try:
        h = int(hour_s)
        m = int(min_s) if min_s is not None else 0
    except ValueError:
        return None
    if not (0 <= m <= 59):
        return None
    if has_ampm:
        ap = ampm_s.lower().replace(".", "")
        if not (1 <= h <= 12):
            # tolerate 0-23 with am/pm marker by mod 12
            if not (0 <= h <= 23):
                return None
            h = h % 12
            if ap == "pm":
                h += 12
            return "%02d:%02d" % (h, m)
        h = h % 12
        if ap == "pm":
            h += 12
        return "%02d:%02d" % (h, m)
    if not (0 <= h <= 23):
        return None
    return "%02d:%02d" % (h, m)


def _attach_time(text, date_end):
    tail = text[date_end:date_end + 24]
    mm = _TIME_RE.match(tail)
    if not mm:
        return None, date_end
    at_part, hour_s, min_s, ampm_s = mm.group(1), mm.group(2), mm.group(3), mm.group(4)
    has_at = "at" in at_part.lower()
    has_colon = min_s is not None
    parsed = _parse_time(hour_s, min_s, ampm_s, has_at, has_colon)
    if parsed is None:
        return None, date_end
    return parsed, date_end + mm.end()


def find_dates(text, today):
    cands = []  # (start, -len, due_date, span_end_no_time, date_end)
    for mm in _ISO_RE.finditer(text):
        try:
            d = datetime.date.fromisoformat(mm.group(1))
        except ValueError:
            continue
        cands.append((mm.start(), -len(mm.group(0)), d, mm.start(), mm.end()))
    for mm in _TODAY_RE.finditer(text):
        cands.append((mm.start(), -len(mm.group(0)), today, mm.start(), mm.end()))
    for mm in _TOMORROW_RE.finditer(text):
        d = today + datetime.timedelta(days=1)
        cands.append((mm.start(), -len(mm.group(0)), d, mm.start(), mm.end()))
    for mm in _NEXT_WEEK_RE.finditer(text):
        d = today + datetime.timedelta(days=7)
        cands.append((mm.start(), -len(mm.group(0)), d, mm.start(), mm.end()))
    for mm in _IN_N_RE.finditer(text):
        n = int(mm.group(1))
        unit = mm.group(2).lower()
        delta = n * 7 if unit.startswith("week") else n
        d = today + datetime.timedelta(days=delta)
        cands.append((mm.start(), -len(mm.group(0)), d, mm.start(), mm.end()))
    for mm in _NEXT_WDAY_RE.finditer(text):
        target = WEEKDAYS[mm.group(1).lower()]
        delta = (target - today.weekday()) % 7
        if delta == 0:
            delta = 7
        d = today + datetime.timedelta(days=delta)
        cands.append((mm.start(), -len(mm.group(0)), d, mm.start(), mm.end()))
    for mm in _WDAY_RE.finditer(text):
        # Skip bare weekday that is the weekday part of a 'next <weekday>' match:
        # it starts later than the 'next ...' match; earliest-wins sorting handles
        # precedence, but avoid double candidates at overlapping positions.
        target = WEEKDAYS[mm.group(1).lower()]
        delta = (target - today.weekday()) % 7
        if delta == 0:
            delta = 7
        d = today + datetime.timedelta(days=delta)
        cands.append((mm.start(), -len(mm.group(0)), d, mm.start(), mm.end()))

    if not cands:
        return {"due_date": None, "due_datetime": None, "spans": []}

    # Leftmost wins; longer match wins ties (e.g. 'next monday' vs inner 'monday').
    cands.sort(key=lambda c: (c[0], c[1]))
    # Filter overlapping bare-weekday duplicates: keep first candidate that starts
    # at or after the previously chosen span... simpler: pick the single earliest.
    start, _, due, span_s, date_e = cands[0]

    # If earliest candidate is a bare weekday nested inside a 'next <weekday>'
    # starting at the same... no — 'next monday' starts earlier, so it wins.
    # But bare regex also yields inner 'monday'; earliest sort already prefers
    # the 'next monday' match. Nothing more to do for single-date V1.
    time_str, span_e = _attach_time(text, date_e)
    if time_str is not None:
        return {
            "due_date": str(due),
            "due_datetime": "%sT%s" % (due, time_str),
            "spans": [(span_s, span_e)],
        }
    return {"due_date": str(due), "due_datetime": None, "spans": [(span_s, date_e)]}
