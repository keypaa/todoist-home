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
