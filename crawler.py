import json
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse, urldefrag

import requests
import tldextract
from bs4 import BeautifulSoup

DEFAULT_HEADERS = {
    "User-Agent": "RecipeCrawlBot/1.0 (+https://example.local; contact: you@example.local)"
}

@dataclass
class CrawlOptions:
    max_pages: int = 25
    max_candidates: int = 300
    same_domain_only: bool = True
    delay_seconds: float = 0.4
    timeout_seconds: int = 15
    verify_recipes: bool = True


def _normalize_url(url: str) -> str:
    url = url.strip()
    # remove fragments
    url, _frag = urldefrag(url)
    # strip trailing whitespace
    return url


def _get_reg_domain(url: str) -> str:
    parts = tldextract.extract(url)
    if not parts.domain:
        return ""
    return ".".join([p for p in [parts.domain, parts.suffix] if p])


def _same_reg_domain(a: str, b: str) -> bool:
    return _get_reg_domain(a) == _get_reg_domain(b)


def fetch_html(url: str, timeout: int, headers: Optional[Dict[str, str]] = None) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    try:
        r = requests.get(url, timeout=timeout, headers=headers or DEFAULT_HEADERS)
        ct = r.headers.get("Content-Type", "")
        if r.status_code >= 400:
            return None, r.status_code, f"HTTP {r.status_code}"
        if "text/html" not in ct and "application/xhtml+xml" not in ct and ct:
            return None, r.status_code, f"Non-HTML Content-Type: {ct}"
        return r.text, r.status_code, None
    except requests.RequestException as e:
        return None, None, str(e)


def extract_links(page_url: str, html: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    links: List[str] = []
    for a in soup.select("a[href]"):
        href = a.get("href")
        if not href:
            continue
        href = href.strip()
        if href.startswith("mailto:") or href.startswith("tel:") or href.startswith("javascript:"):
            continue
        abs_url = urljoin(page_url, href)
        abs_url = _normalize_url(abs_url)
        links.append(abs_url)
    # de-dupe while preserving order
    seen = set()
    out = []
    for u in links:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _looks_like_recipe_url(url: str) -> bool:
    u = url.lower()
    # Heuristics: many sites include these patterns
    return any(p in u for p in ["/recipe", "/recipes", "recipe="]) or bool(re.search(r"\brecipe\b", u))


def _jsonld_contains_recipe(obj) -> bool:
    # JSON-LD can be dict, list, or graph
    if isinstance(obj, list):
        return any(_jsonld_contains_recipe(x) for x in obj)
    if isinstance(obj, dict):
        # handle @graph
        if "@graph" in obj and isinstance(obj["@graph"], list):
            if any(_jsonld_contains_recipe(x) for x in obj["@graph"]):
                return True
        t = obj.get("@type") or obj.get("type")
        if isinstance(t, list):
            if any(str(x).lower() == "recipe" for x in t):
                return True
        if isinstance(t, str) and t.lower() == "recipe":
            return True
        # sometimes nested
        return any(_jsonld_contains_recipe(v) for v in obj.values() if isinstance(v, (dict, list)))
    return False


def is_recipe_page(html: str) -> Tuple[bool, Optional[str]]:
    soup = BeautifulSoup(html, "lxml")

    # Microdata
    if soup.select_one('[itemtype*="schema.org/Recipe"], [itemtype*="https://schema.org/Recipe"], [itemtype*="http://schema.org/Recipe"]'):
        title = soup.title.get_text(strip=True) if soup.title else None
        return True, title

    # JSON-LD
    for s in soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)}):
        txt = (s.string or "").strip()
        if not txt:
            continue
        # Some pages have multiple JSON blobs or invalid JSON; try best-effort parsing
        try:
            data = json.loads(txt)
            if _jsonld_contains_recipe(data):
                title = soup.title.get_text(strip=True) if soup.title else None
                return True, title
        except json.JSONDecodeError:
            # try to salvage by finding first/last brace
            start = txt.find("{")
            end = txt.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    data = json.loads(txt[start : end + 1])
                    if _jsonld_contains_recipe(data):
                        title = soup.title.get_text(strip=True) if soup.title else None
                        return True, title
                except Exception:
                    pass

    title = soup.title.get_text(strip=True) if soup.title else None
    return False, title


def crawl_for_recipes(start_url: str, options: CrawlOptions) -> List[Dict]:
    start_url = _normalize_url(start_url)
    parsed = urlparse(start_url)
    if not parsed.scheme:
        start_url = "https://" + start_url

    base_domain = _get_reg_domain(start_url)

    queue: List[Tuple[str, int]] = [(start_url, 0)]
    visited: Set[str] = set()
    candidates: List[str] = []
    results: List[Dict] = []

    pages_fetched = 0

    while queue and pages_fetched < options.max_pages and len(candidates) < options.max_candidates:
        url, depth = queue.pop(0)
        url = _normalize_url(url)
        if url in visited:
            continue
        visited.add(url)

        if options.same_domain_only and base_domain and not _same_reg_domain(url, start_url):
            continue

        html, status, err = fetch_html(url, timeout=options.timeout_seconds)
        pages_fetched += 1
        time.sleep(options.delay_seconds)

        if not html:
            results.append({
                "url": url,
                "source_page": None,
                "is_candidate": False,
                "is_recipe": False,
                "title": None,
                "http_status": status,
                "error": err,
            })
            continue

        # Extract links from this page
        links = extract_links(url, html)
        for link in links:
            if options.same_domain_only and base_domain and not _same_reg_domain(link, start_url):
                continue
            if link not in visited and len(queue) < options.max_pages * 20:
                # keep crawl shallow-ish by default
                queue.append((link, depth + 1))

            if _looks_like_recipe_url(link):
                candidates.append(link)
                if len(candidates) >= options.max_candidates:
                    break

        # Also consider the current page itself a candidate if it looks like a recipe
        if _looks_like_recipe_url(url) and url not in candidates:
            candidates.append(url)

    # De-dupe candidates while preserving order
    seen = set()
    deduped_candidates = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            deduped_candidates.append(c)

    # Verify candidates
    for c in deduped_candidates:
        row = {
            "url": c,
            "source_page": start_url,
            "is_candidate": True,
            "is_recipe": False,
            "title": None,
            "http_status": None,
            "error": None,
        }
        if options.verify_recipes:
            html, status, err = fetch_html(c, timeout=options.timeout_seconds)
            row["http_status"] = status
            row["error"] = err
            if html:
                ok, title = is_recipe_page(html)
                row["is_recipe"] = ok
                row["title"] = title
        results.append(row)

    return results
