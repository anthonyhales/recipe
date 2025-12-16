
import threading, time
from crawler import crawl
from db import get_conn

STOP = False

def run(start_url):
    global STOP
    STOP = False
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM recipes")
    conn.commit()

    for url, title in crawl(start_url):
        if STOP:
            break
        cur.execute(
            "INSERT OR IGNORE INTO recipes VALUES (?,?,1)",
            (url, title)
        )
        conn.commit()

    cur.execute("DELETE FROM crawl_state")
    cur.execute("INSERT INTO crawl_state VALUES (?)", ("finished",))
    conn.commit()
    conn.close()

def start_bg(url):
    t = threading.Thread(target=run, args=(url,), daemon=True)
    t.start()
