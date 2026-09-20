from app import nlp
def test_registry_detect_defaults_en():
    assert nlp.detect("Buy milk tomorrow") == "en"
    assert nlp.detect("Acheter du lait demain") == "fr"
def test_base_extract_tokens():
    from app.nlp.base import extract_tokens
    r = extract_tokens("Buy milk #Shopping @errands p1")
    assert r["project"] == "Shopping" and "errands" in r["labels"] and r["priority"] == 4
