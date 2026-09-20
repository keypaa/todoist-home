LANGUAGES = {}
def register(code, module): LANGUAGES[code] = module
FR_MARKERS = ("aujourd", "demain", "lun", "mar", "mer", "jeu", "ven", "sam", "dim", "semaine", "prochain", "dans ", "mois", "janv", "fév", "fev", "mars", "avr", "mai", "juin", "juil", "août", "aout", "sept", "oct", "nov", "déc", "dec")
def detect(text):
    low = " " + text.lower() + " "
    return "fr" if any(m in low for m in FR_MARKERS) else "en"
