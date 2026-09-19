import sqlite3, os
SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, email TEXT);
CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT '1', name TEXT NOT NULL, is_archived INTEGER NOT NULL DEFAULT 0, is_deleted INTEGER NOT NULL DEFAULT 0, order_key TEXT DEFAULT 'a0');
CREATE TABLE IF NOT EXISTS sections(id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL, is_archived INTEGER NOT NULL DEFAULT 0, is_deleted INTEGER NOT NULL DEFAULT 0, order_key TEXT DEFAULT 'a0');
CREATE TABLE IF NOT EXISTS labels(id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT '1', name TEXT NOT NULL, is_deleted INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT '1', content TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', project_id TEXT NOT NULL, section_id TEXT, parent_id TEXT, priority INTEGER NOT NULL DEFAULT 1, due_date TEXT, due_datetime TEXT, due_timezone TEXT, due_string TEXT, due_lang TEXT DEFAULT 'en', is_recurring INTEGER NOT NULL DEFAULT 0, deadline_date TEXT, duration_amount INTEGER, duration_unit TEXT, responsible_uid TEXT, order_key TEXT DEFAULT 'a0', completed INTEGER NOT NULL DEFAULT 0, is_deleted INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS task_labels(task_id TEXT NOT NULL, label_id TEXT NOT NULL, PRIMARY KEY(task_id,label_id));
CREATE TABLE IF NOT EXISTS reminders(id TEXT PRIMARY KEY, task_id TEXT NOT NULL, minute_offset INTEGER, due_string TEXT, is_deleted INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS day_orders(task_id TEXT NOT NULL, day TEXT NOT NULL, ord INTEGER NOT NULL, PRIMARY KEY(task_id, day));
CREATE TABLE IF NOT EXISTS sync_state(token TEXT PRIMARY KEY, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS idempotency(key TEXT PRIMARY KEY, response TEXT NOT NULL);
"""
def get_db_path():
    base = os.environ.get("OPENDOIST_DB", os.path.expanduser("~/.local/share/opendoist/opendoist.db"))
    d = os.path.dirname(base)
    if d: os.makedirs(d, exist_ok=True)
    return base
def get_db(path=None):
    p = path or get_db_path()
    if p != ":memory:":
        d = os.path.dirname(p)
        if d: os.makedirs(d, exist_ok=True)
    con = sqlite3.connect(p, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA busy_timeout=5000;")
    return con
def init_db(path=None):
    con = get_db(path)
    con.executescript(SCHEMA)
    con.execute("INSERT OR IGNORE INTO users(id,email) VALUES('1','local@opendoist')")
    con.execute("INSERT OR IGNORE INTO projects(id,name) VALUES('inbox','Inbox')")
    con.commit()
    return con
