"""web.py - ONLINE mode: searches the internet and reads the top pages.

Uses only Python's built-in tools (no extra packages, no API key):
  1. asks DuckDuckGo's plain-HTML search page for results
  2. downloads the top few pages and strips them down to readable text
  3. keeps the paragraphs that share the most words with your question
If there is no internet, it raises WebError and the chat says so.
"""
from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
SEARCH_URL = "https://html.duckduckgo.com/html/"
STOP = set("the a an and or of to in on for is are was were be how what why when which who does do "
           "with by as at it this that from can i you me my your about explain".split())


class WebError(Exception):
    pass


def _get(url: str, timeout: float = 8, data: bytes | None = None) -> str:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        ctype = r.headers.get("Content-Type", "")
        if "html" not in ctype and "text" not in ctype:
            return ""
        raw = r.read(1_500_000)
        charset = r.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def _clean(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def search(query: str, n: int = 6) -> list[dict]:
    try:
        page = _get(SEARCH_URL, data=urllib.parse.urlencode({"q": query}).encode())
    except Exception as e:
        raise WebError(f"Could not reach the internet ({e.__class__.__name__}). Check your connection, "
                       "or switch to Offline mode to use your books.")
    results = []
    for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]+class="result__a"|$)',
                         page, re.S):
        href, title, rest = m.group(1), _clean(m.group(2)), m.group(3)
        href = html.unescape(href)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        if "uddg" in q:
            href = q["uddg"][0]
        if not href.startswith("http") or "duckduckgo.com" in href:
            continue
        snip = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', rest, re.S)
        results.append({"title": title, "url": href, "snippet": _clean(snip.group(1)) if snip else ""})
        if len(results) >= n:
            break
    return results


def _page_text(url: str) -> str:
    try:
        page = _get(url)
    except Exception:
        return ""
    page = re.sub(r"(?is)<(script|style|nav|header|footer|aside|form|noscript|svg)[^>]*>.*?</\1>", " ", page)
    paras = re.findall(r"(?is)<(?:p|li|h2|h3)[^>]*>(.*?)</(?:p|li|h2|h3)>", page)
    return "\n".join(t for t in (_clean(p) for p in paras) if len(t.split()) >= 8)


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP and len(w) > 2}


def _best_parts(text: str, query: str, max_words: int) -> str:
    qw = _words(query)
    paras = [p for p in text.split("\n") if p]
    scored = sorted(((len(qw & _words(p)), i, p) for i, p in enumerate(paras)), reverse=True)
    chosen, total = [], 0
    for score, i, p in scored:
        if score == 0 and chosen:
            break
        w = len(p.split())
        if total + w > max_words:
            continue
        chosen.append((i, p)); total += w
    return " ".join(p for _, p in sorted(chosen))


def gather(query: str, pages: int = 3, words_per_page: int = 170) -> list[dict]:
    """Search, read the top pages, and return short relevant extracts with their links."""
    results = search(query)
    if not results:
        return []
    top = results[:pages]
    with ThreadPoolExecutor(max_workers=pages) as pool:
        texts = list(pool.map(_page_text, [r["url"] for r in top]))
    out = []
    for r, text in zip(top, texts):
        extract = _best_parts(text, query, words_per_page) if text else ""
        if len(extract.split()) < 25:          # page blocked or empty: fall back to the search snippet
            extract = r["snippet"]
        if extract:
            out.append({"title": r["title"], "url": r["url"], "text": extract})
    return out
