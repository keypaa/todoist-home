"""FR date parsing for OpenDoist V1 (Phase 4 Task 3). Parity with app.nlp.en."""
import datetime
import re

# Accent-insensitive matching: normalize (e->e etc) for matching, keep spans
# on the original text. The map is 1 char -> 1 char (plus 1-char quote folds)
# so indices into the normalized text are valid for the original text.
_ACCENT_MAP = str.maketrans({
    "à": "a", "â": "a", "ä": "a",
    "é": "e", "è": "e", "ê": "e", "ë": "e",
    "î": "i", "ï": "i",
    "ô": "o", "ö": "o",
    "ù": "u", "û": "u", "ü": "u",
    "ÿ": "y", "ç": "c",
})


def _norm(s):
    return s.replace("’", "'").replace("‘", "'").lower().translate(_ACCENT_MAP)


WEEKDAYS = {
    "lundi": 0, "lun": 0,
    "mardi": 1, "mar": 1,
    "mercredi": 2, "mer": 2,
    "jeudi": 3, "jeu": 3,
    "vendredi": 4, "ven": 4,
    "samedi": 5, "sam": 5,
    "dimanche": 6, "dim": 6,
}

MONTHS = {
    "janvier": 1, "jan": 1,
    "fevrier": 2, "fev": 2,
    "mars": 3, "mar": 3,
    "avril": 4, "avr": 4,
    "mai": 5,
    "juin": 6, "jun": 6,
    "juillet": 7, "juil": 7, "jul": 7,
    "aout": 8, "aou": 8,
    "septembre": 9, "sept": 9, "sep": 9,
    "octobre": 10, "oct": 10,
    "novembre": 11, "nov": 11,
    "decembre": 12, "dec": 12,
}


def _alt(keys):
    return "|".join(sorted(keys, key=len, reverse=True))


_WDAY_ALT = _alt(WEEKDAYS)
_MONTH_ALT = _alt(MONTHS)

_ISO_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_DMY_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_MONTH_RE = re.compile(r"\b(?:le\s+)?(\d{1,2})\s+(%s)\b" % _MONTH_ALT)
_AUJ_RE = re.compile(r"\baujourd'hui\b|\baujourdhui\b|\bauj\b")
_APRES_RE = re.compile(r"\bapres[\s-]*demain\b")
_DEMAIN_RE = re.compile(r"\bdemain\b")
_NEXT_WEEK_RE = re.compile(r"\b(?:la\s+)?semaine\s+prochaine\b")
_IN_N_RE = re.compile(r"\bdans\s+(\d+)\s+(jours?|semaines?)\b")
_NEXT_WDAY_RE = re.compile(r"\b(%s)\s+prochain(?:e|s|es)?\b" % _WDAY_ALT)
_WDAY_RE = re.compile(r"\b(%s)\b" % _WDAY_ALT)

# Time attached immediately after a date match: optional 'a' (a), then
# H(hMM?|:MM)? — requires at least one of: 'a' prefix, 'h' suffix, or colon
# (so bare numbers like the day in "22 septembre" never attach as a time).
_TIME_RE = re.compile(r"^(\s+(?:a\s+)?)(\d{1,2})(?:\s*(h)\s*(\d{2})?|:(\d{2}))?\b")


def _parse_time(hour_s, h_min_s, colon_min_s, has_a, has_h, has_colon):
    if not (has_a or has_h or has_colon):
        return None
    try:
        h = int(hour_s)
        m_s = h_min_s if h_min_s is not None else colon_min_s
        m = int(m_s) if m_s is not None else 0
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return "%02d:%02d" % (h, m)


def _attach_time(ntext, date_end):
    tail = ntext[date_end:date_end + 24]
    mm = _TIME_RE.match(tail)
    if not mm:
        return None, date_end
    at_part, hour_s, h_mark, h_min, c_min = (
        mm.group(1), mm.group(2), mm.group(3), mm.group(4), mm.group(5))
    parsed = _parse_time(hour_s, h_min, c_min,
                         "a" in at_part, h_mark is not None, c_min is not None)
    if parsed is None:
        return None, date_end
    return parsed, date_end + mm.end()


def _month_date(day, month, today):
    try:
        d = datetime.date(today.year, month, day)
    except ValueError:
        return None
    if d < today:
        try:
            d = datetime.date(today.year + 1, month, day)
        except ValueError:
            return None
    return d


def find_dates(text, today):
    ntext = _norm(text)
    cands = []  # (start, -len, due_date, span_start, date_end, kind)
    for mm in _ISO_RE.finditer(ntext):
        try:
            d = datetime.date.fromisoformat(mm.group(1))
        except ValueError:
            continue
        cands.append((mm.start(), -len(mm.group(0)), d, mm.start(), mm.end(), "iso"))
    for mm in _DMY_RE.finditer(ntext):
        try:
            d = datetime.date(int(mm.group(3)), int(mm.group(2)), int(mm.group(1)))
        except ValueError:
            continue
        cands.append((mm.start(), -len(mm.group(0)), d, mm.start(), mm.end(), "dmy"))
    for mm in _MONTH_RE.finditer(ntext):
        d = _month_date(int(mm.group(1)), MONTHS[mm.group(2)], today)
        if d is None:
            continue
        cands.append((mm.start(), -len(mm.group(0)), d, mm.start(), mm.end(), "month"))
    for mm in _AUJ_RE.finditer(ntext):
        cands.append((mm.start(), -len(mm.group(0)), today, mm.start(), mm.end(), "rel"))
    for mm in _APRES_RE.finditer(ntext):
        d = today + datetime.timedelta(days=2)
        cands.append((mm.start(), -len(mm.group(0)), d, mm.start(), mm.end(), "rel"))
    for mm in _DEMAIN_RE.finditer(ntext):
        d = today + datetime.timedelta(days=1)
        cands.append((mm.start(), -len(mm.group(0)), d, mm.start(), mm.end(), "rel"))
    for mm in _NEXT_WEEK_RE.finditer(ntext):
        d = today + datetime.timedelta(days=7)
        cands.append((mm.start(), -len(mm.group(0)), d, mm.start(), mm.end(), "rel"))
    for mm in _IN_N_RE.finditer(ntext):
        n = int(mm.group(1))
        delta = n * 7 if mm.group(2).startswith("semaine") else n
        d = today + datetime.timedelta(days=delta)
        cands.append((mm.start(), -len(mm.group(0)), d, mm.start(), mm.end(), "rel"))
    for mm in _NEXT_WDAY_RE.finditer(ntext):
        target = WEEKDAYS[mm.group(1)]
        delta = (target - today.weekday()) % 7
        if delta == 0:
            delta = 7
        d = today + datetime.timedelta(days=delta + 7)
        cands.append((mm.start(), -len(mm.group(0)), d, mm.start(), mm.end(), "next_wday"))
    for mm in _WDAY_RE.finditer(ntext):
        target = WEEKDAYS[mm.group(1)]
        delta = (target - today.weekday()) % 7
        if delta == 0:
            delta = 7
        d = today + datetime.timedelta(days=delta)
        cands.append((mm.start(), -len(mm.group(0)), d, mm.start(), mm.end(), "wday"))

    if not cands:
        return {"due_date": None, "due_datetime": None, "spans": []}

    # A bare weekday directly qualifying an explicit date ("mardi 22 septembre")
    # is apposition, not the date — the explicit date wins.
    explicit = [c for c in cands if c[5] in ("iso", "dmy", "month")]
    drop = set()
    for i, c in enumerate(cands):
        if c[5] not in ("wday", "next_wday"):
            continue
        for e in explicit:
            if e[0] >= c[4] and ntext[c[4]:e[0]].strip() == "":
                drop.add(i)
                break
    cands = [c for i, c in enumerate(cands) if i not in drop]
    if not cands:
        return {"due_date": None, "due_datetime": None, "spans": []}

    # Leftmost wins; longer match wins ties (e.g. 'apres-demain' vs 'demain').
    cands.sort(key=lambda c: (c[0], c[1]))
    _, _, due, span_s, date_e, _ = cands[0]

    time_str, span_e = _attach_time(ntext, date_e)
    if time_str is not None:
        return {
            "due_date": str(due),
            "due_datetime": "%sT%s" % (due, time_str),
            "spans": [(span_s, span_e)],
        }
    return {"due_date": str(due), "due_datetime": None, "spans": [(span_s, date_e)]}
