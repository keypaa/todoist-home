import time, secrets


def new_id():
    return str(int(time.time() * 1000)) + secrets.token_hex(4)


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def task_to_api(r, labels=None):
    due = None
    if r["due_date"]:
        due = {"date": r["due_date"], "timezone": r["due_timezone"], "string": r["due_string"] or "", "lang": r["due_lang"] or "en", "is_recurring": bool(r["is_recurring"])}
        if r["due_datetime"]:
            due["datetime"] = r["due_datetime"]
    d = {"id": r["id"], "content": r["content"], "description": r["description"] or "", "project_id": r["project_id"], "section_id": r["section_id"], "parent_id": r["parent_id"], "priority": r["priority"], "labels": labels or [], "order": 0, "order_key": r["order_key"], "completed": bool(r["completed"]), "created_at": r["created_at"]}
    if due:
        d["due"] = due
    if r["deadline_date"]:
        d["deadline"] = {"date": r["deadline_date"]}
    if r["duration_amount"]:
        d["duration"] = {"amount": r["duration_amount"], "unit": r["duration_unit"] or "minute"}
    if r["responsible_uid"]:
        d["responsible_uid"] = r["responsible_uid"]
    return d
