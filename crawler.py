
import json, re, time
from urllib.parse import urljoin, urldefrag
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "RecipeCrawlBot/1.0 (contact: admin@example.com)"}

def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=15)
    if "text/html" not in r.headers.get("Content-Type",""):
        return None
    return r.text

def extract_links(base, html):
    soup = BeautifulSoup(html, "lxml")
    links = set()
    for a in soup.select("a[href]"):
        u = urljoin(base, a["href"])
        u, _ = urldefrag(u)
        links.add(u)
    return links

def is_recipe(html):
    soup = BeautifulSoup(html, "lxml")
    if soup.select_one('[itemtype*="Recipe"]'):
        return True, soup.title.text if soup.title else None
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "")
            if "Recipe" in json.dumps(data):
                return True, soup.title.text if soup.title else None
        except Exception:
            pass
    return False, soup.title.text if soup.title else None

def crawl(start_url, limit=500):
    seen, found = set(), []
    queue = [start_url]
    while queue and len(seen) < limit:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            html = fetch(url)
        except Exception:
            continue
        if not html:
            continue
        ok, title = is_recipe(html)
        if ok:
            found.append((url, title))
        for l in extract_links(url, html):
            if start_url.split("/")[2] in l:
                queue.append(l)
        time.sleep(0.3)
    return found
