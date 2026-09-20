import re
LANGUAGES = {}
def register(code, module): LANGUAGES[code] = module
FR_MARKERS = ("aujourd", "demain", "lun", "mar", "mer", "jeu", "ven", "sam", "dim", "semaine", "prochain", "dans ", "mois", "janv", "fév", "fev", "mars", "avr", "mai", "juin", "juil", "août", "aout", "sept", "oct", "nov", "déc", "dec")
_FR_RE = re.compile(r"\b(?:%s)\b" % "|".join(re.escape(m.strip()) for m in FR_MARKERS), re.IGNORECASE)
def detect(text):
    return "fr" if _FR_RE.search(text) else "en"


try:
    from app.nlp import en as _en_mod
    LANGUAGES["en"] = _en_mod
except ImportError:
    pass
