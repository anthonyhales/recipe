
import sqlite3
from pathlib import Path

DB_PATH = Path("data.db")

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS crawl_state (status TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS recipes (url TEXT PRIMARY KEY, title TEXT, is_recipe INTEGER)")
    conn.commit()
    conn.close()
