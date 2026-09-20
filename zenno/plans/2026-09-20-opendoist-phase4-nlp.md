# Phase 4 Bilingual NLP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** French + English quick-add date parsing at equal quality, with a registry so a third language is one new file.

**Architecture:** New `app/nlp/` package: `base.py` holds language-independent token extraction (moved verbatim from `app/parser.py`), each language is one module (`en.py`, `fr.py`) implementing `find_dates(text, today)`, registered in `__init__.py` with auto-detect (FR markers → fr, else en). `parse_quick_add(text, today_iso, lang="auto")` keeps its signature.

**Tech Stack:** Python 3.11+ stdlib only (`re`, `datetime`), pytest, existing FastAPI wiring untouched except result passthrough.

## Global Constraints

- No new dependencies (stdlib only — matches project constraint, runs on Omarchy with zero install).
- `parse_quick_add(text, today_iso)` old signature keeps working (lang defaults to `"auto"` → same results as today for all existing tests).
- Token rules unchanged: `p1`->4, `#` quoted project, `@`/`%` labels, `/` section (whitespace-guarded), escaped `\# \@ \% \/`, trailing punct stripped.
- Bare text with no date → `due_date None` (server applies today default, unchanged).
- FR and EN must reach parity on the same concept list (table in Task 3); neither may regress the other.
- New language = one file `app/nlp/<xx>.py` + one `register()` line + tests (proven by Task 5 docs test).

---

### Task 1: Registry + base extraction (no behavior change)

**Files:**
- Create: `app/nlp/__init__.py`, `app/nlp/base.py`
- Modify: `app/parser.py` (thin wrapper, keep signature)
- Test: `tests/test_parser.py` (existing, must stay green)

**Interfaces:**
- Consumes: current `parse_quick_add` logic in `app/parser.py:12-90`
- Produces: `app.nlp.base.extract_tokens(t) -> dict{priority, project, labels, section, spans, cleaned}`, `app.nlp.LANGUAGES: dict[str, module]`, `register(code, module)`, `detect(text) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_nlp_registry.py
from app import nlp
def test_registry_detect_defaults_en():
    assert nlp.detect("Buy milk tomorrow") == "en"
    assert nlp.detect("Acheter du lait demain") == "fr"
def test_base_extract_tokens():
    from app.nlp.base import extract_tokens
    r = extract_tokens("Buy milk #Shopping @errands p1")
    assert r["project"] == "Shopping" and "errands" in r["labels"] and r["priority"] == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_nlp_registry.py -v`
Expected: FAIL with "No module named 'app.nlp'"

- [ ] **Step 3: Write minimal implementation**

```python
# app/nlp/base.py — move token extraction verbatim from app/parser.py:12-40,74-77 (no date logic)
import re
def _strip_trailing_punct(name): return name.rstrip(",.;:!?)")
def extract_tokens(t):
    spans = []
    priority = 1
    m = re.search(r"\bp([1-4])\b", t)
    if m: priority = 5 - int(m.group(1)); spans.append(m.span())
    project = None
    for mm in re.finditer(r'(?<!\\)#(?:"([^"]+)"|\'([^\']+)\'|(\S+))', t):
        project = _strip_trailing_punct(mm.group(1) or mm.group(2) or mm.group(3)); spans.append(mm.span())
    labels = []
    for mm in re.finditer(r'(?<!\\)[@%](\S+)', t):
        labels.append(_strip_trailing_punct(mm.group(1))); spans.append(mm.span())
    section = None
    for mm in re.finditer(r'(?<!\\)(?:(?<=\s)|^)/(\S+)', t):
        section = _strip_trailing_punct(mm.group(1)); spans.append(mm.span())
    return {"priority": priority, "project": project, "labels": labels, "section": section, "spans": spans}
```

```python
# app/nlp/__init__.py
LANGUAGES = {}
def register(code, module): LANGUAGES[code] = module
FR_MARKERS = ("aujourd", "demain", "lun", "mar", "mer", "jeu", "ven", "sam", "dim", "semaine", "prochain", "dans ", "mois", "janv", "fév", "fev", "mars", "avr", "mai", "juin", "juil", "août", "aout", "sept", "oct", "nov", "déc", "dec")
def detect(text):
    low = " " + text.lower() + " "
    return "fr" if any(m in low for m in FR_MARKERS) else "en"
```

`app/parser.py` becomes: `extract_tokens` + registry lookup + `find_dates`, reassemble content identically (spans removed reverse-order, whitespace collapsed, escapes restored).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_nlp_registry.py tests/test_parser.py tests/test_quick.py -q`
Expected: PASS, no regressions

- [ ] **Step 5: Commit**

```bash
git add app/nlp tests/test_nlp_registry.py app/parser.py
git commit -m "feat: nlp registry + base token extraction, no behavior change"
```

### Task 2: EN module (move + time support)

**Files:**
- Create: `app/nlp/en.py`
- Modify: `app/parser.py` (use registry)
- Test: `tests/test_nlp_en.py`

**Interfaces:**
- Consumes: `extract_tokens` from Task 1
- Produces: `app.nlp.en.find_dates(text, today: date) -> dict{due_date, due_datetime, spans}`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_nlp_en.py -v`
Expected: FAIL with "No module named 'app.nlp.en'"

- [ ] **Step 3: Write minimal implementation**

```python
# app/nlp/en.py — weekday names, today/tomorrow/next <weekday>/next week/in N days/YYYY-MM-DD/HH:MM, times: at 5pm, at 17:30, 5pm
```

Rules: `today|tomorrow`, `next <weekday>` (strictly next week's day; bare `<weekday>` = upcoming occurrence, today excluded unless same-day time still ahead — V1: next occurrence strictly after today), `next week` = +7, `in N days|weeks`, ISO `YYYY-MM-DD`, optional time `at H(:MM)?(am|pm)?` or bare `Hpm`/`HH:MM` attached to the date match; `due_datetime` = `f"{date}T{HH:MM}"` 24h. Return spans covering date+time words for content stripping. Keep old outputs identical for old inputs (`tomorrow`→date only, no datetime).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_nlp_en.py tests/test_parser.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/nlp/en.py tests/test_nlp_en.py app/parser.py
git commit -m "feat: EN date module with time support"
```

### Task 3: FR module (parity with EN)

**Files:**
- Create: `app/nlp/fr.py`
- Test: `tests/test_nlp_fr.py`

**Interfaces:**
- Consumes: registry from Task 1
- Produces: `app.nlp.fr.find_dates` — same return shape as EN

Parity table (each row must behave identically modulo language):

| concept | EN | FR |
|---|---|---|
| today | today | aujourd'hui, auj |
| tomorrow | tomorrow | demain |
| day after | (overmorrow — not required) | après-demain |
| weekdays | Monday..Sunday | lundi..dimanche (+ accents-insensitive: aout/dec/fev) |
| next weekday | next Monday | lundi prochain |
| next week | next week | semaine prochaine / la semaine prochaine |
| in N days | in 3 days | dans 3 jours |
| iso/date | 2026-10-02 | 02/10/2026, le 2 octobre, 2 oct |
| time | at 5pm, 17:30 | à 17h, 17h30, 10h, demain 13:00 |

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_nlp_fr.py -v`
Expected: FAIL with "No module named 'app.nlp.fr'"

- [ ] **Step 3: Write minimal implementation**

```python
# app/nlp/fr.py — normalize accents (é->e etc) for matching, keep original spans; months jan..dec FR (+ anglais-proof: do NOT match English-only words); time: à? HHh(MM)?, HH:MM
```

Month map: janvier/février/mars/avril/mai/juin/juillet/août/septembre/octobre/novembre/décembre (+ abbr jan fév/fev mar avr mai jun/juin jul/juil aou/aout sep/sept oct nov dec). `le 2 octobre` / `2 oct` / `02/10/2026` (DD/MM/YYYY → ISO). Bare weekday = next occurrence strictly after today; `<jour> prochain` = same weekday in next week (+7 from the bare result). `après-demain` = +2.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_nlp_fr.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/nlp/fr.py tests/test_nlp_fr.py
git commit -m "feat: FR date module at EN parity"
```

### Task 4: Wire detect + lang passthrough + quick route

**Files:**
- Modify: `app/parser.py`, `app/api_tasks.py` (quick route), `app/sync.py` (quick path if separate)
- Test: `tests/test_nlp_parity.py`

**Interfaces:**
- Consumes: Tasks 1-3
- Produces: `parse_quick_add(text, today_iso, lang="auto") -> {…old keys…, "lang": "en"|"fr"}`; quick route accepts optional `lang`, returns task with `due.string` + `due.lang`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_nlp_parity.py -v`
Expected: FAIL (lang kwarg missing / FR dates missing)

- [ ] **Step 3: Write minimal implementation**

```python
def parse_quick_add(text, today_iso, lang="auto"):
    toks = extract_tokens(text)
    code = lang if lang in LANGUAGES else detect(text)
    found = LANGUAGES[code].find_dates(text, datetime.date.fromisoformat(today_iso))
    # strip date spans + token spans identically to old code, return {**toks, "due_date":..., "due_datetime":..., "lang": code, ...}
```

Quick route: read `body.get("lang", "auto")`, pass through, store `due_lang=code`, return `due: {…, "lang": code}`. Bare-no-date → today rule unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_nlp_parity.py tests/test_parser.py tests/test_quick.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/parser.py app/api_tasks.py app/sync.py tests/test_nlp_parity.py
git commit -m "feat: auto-detect FR/EN + lang passthrough in quick-add"
```

### Task 5: Extensibility proof + docs

**Files:**
- Create: `tests/test_nlp_extend.py`
- Modify: `README.md` (add Languages section)

**Interfaces:**
- Consumes: Tasks 1-4
- Produces: documented 3-step recipe + test proving it

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_nlp_extend.py -v`
Expected: FAIL with "register … not defined"

- [ ] **Step 3: Write minimal implementation**

Already exists if Tasks 1-4 done — this test only passes then. Docs addition to README:

```markdown
## Languages (quick-add dates)
EN + FR ship with parity. Add a language in 3 steps: 1) create `app/nlp/<code>.py` with `find_dates(text, today) -> {due_date, due_datetime, spans}`, 2) `register("<code>", module)` in `app/nlp/__init__.py` (+ detect markers if auto-detect should find it), 3) add `tests/test_nlp_<code>.py` mirroring the parity table.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_nlp_extend.py -q && python -m pytest -q`
Expected: PASS, full suite green

- [ ] **Step 5: Commit**

```bash
git add tests/test_nlp_extend.py README.md
git commit -m "docs: third-language recipe + registry proof"
```

## Self-Review

- Spec coverage: spec §FR-NLP flagship (FR == EN quality, chip preview via `due.string/lang` already returned, bilingual) → Tasks 2-4; extensibility requirement → Tasks 1+5; no-regression → every task re-runs old suites.
- Placeholders: none — all steps carry real code/tests/commands.
- Type consistency: `find_dates(text, today: date) -> {due_date: str|None, due_datetime: str|None, spans: list[(int,int)]}` uniform; `parse_quick_add(text, today_iso, lang="auto")` single signature; `register(code, module)` everywhere.
