"""
Web Search Tool v6.0 — OpenSERP-powered, multi-engine, no API key.
Uses local OpenSERP instance (Docker) for multi-engine search.
Falls back to Wikipedia + DDG Instant if OpenSERP is unavailable.
"""
import logging
import subprocess
import json
import re
import html as html_module

logger = logging.getLogger("web-search")

OPEN_SERP_URL = "http://127.0.0.1:7000"


def _http_get(url, headers=None, timeout=15):
    """HTTP GET via curl."""
    cmd = ["curl", "-sL", "--max-time", str(timeout)]
    default_headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
        "Accept": "application/json, text/html",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if headers:
        default_headers.update(headers)
    for k, v in default_headers.items():
        cmd.extend(["-H", f"{k}: {v}"])
    cmd.append(url)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
        return r.stdout
    except Exception as e:
        logger.warning(f"HTTP GET failed for {url}: {e}")
        return ""


def _search_openserp(query, limit=10):
    """Search via local OpenSERP instance (multi-engine, no API key)."""
    try:
        import urllib.parse
        q = urllib.parse.quote_plus(query)
        url = f"{OPEN_SERP_URL}/mega/search?text={q}&limit={limit}"
        raw = _http_get(url, timeout=20)
        if not raw:
            return []
        data = json.loads(raw)
        results = []
        for r in data.get("results", []):
            title = r.get("title", "")
            url = r.get("url", "")
            snippet = r.get("snippet", "")[:200]
            # Skip Yandex ad redirects
            if "yabs.yandex.ru" in url:
                continue
            if title and url:
                results.append({
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "source": r.get("engine", "openserp")
                })
        return results
    except Exception as e:
        logger.warning(f"OpenSERP search failed: {e}")
        return []


def _search_wikipedia(query, limit=5):
    """Search Wikipedia API (fallback)."""
    try:
        import urllib.parse
        url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={query}&format=json&srlimit={limit}"
        raw = _http_get(url)
        if not raw:
            return []
        data = json.loads(raw)
        results = []
        for item in data.get("query", {}).get("search", []):
            title = item["title"]
            snippet = re.sub(r"<[^>]+>", "", item.get("snippet", ""))[:150]
            url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
            results.append({"title": title, "url": url, "snippet": snippet, "source": "wikipedia"})
        return results
    except Exception as e:
        logger.warning(f"Wikipedia search failed: {e}")
        return []


def _search_ddg_instant(query, limit=5):
    """Search DuckDuckGo Instant Answer API (fallback)."""
    try:
        import urllib.parse
        url = f"https://api.duckduckgo.com/?query={query}&format=json&skip_disambig=1&no_html=1"
        raw = _http_get(url)
        if not raw:
            return []
        data = json.loads(raw)
        results = []
        if data.get("Abstract") and data.get("AbstractURL"):
            results.append({
                "title": data.get("Heading", query),
                "url": data.get("AbstractURL", ""),
                "snippet": data.get("Abstract", "")[:200],
                "source": "ddg"
            })
        for topic in data.get("RelatedTopics", [])[:limit]:
            if isinstance(topic, dict) and topic.get("FirstURL"):
                text = topic.get("Text", "")
                results.append({
                    "title": text[:80],
                    "url": topic["FirstURL"],
                    "snippet": text[:150],
                    "source": "ddg"
                })
        return results[:limit]
    except Exception as e:
        logger.warning(f"DDG Instant search failed: {e}")
        return []


def web_search_handler(query, max_results=10):
    """
    Search the internet. Primary: OpenSERP (multi-engine, local).
    Fallback: Wikipedia + DuckDuckGo Instant.
    No API key required.
    """
    all_results = []

    # Primary: OpenSERP (Bing + Yandex + Google + DDG + Baidu)
    all_results.extend(_search_openserp(query, limit=max_results))

    # Fallback if OpenSERP returns too few results
    if len(all_results) < 3:
        all_results.extend(_search_wikipedia(query, limit=5))
        all_results.extend(_search_ddg_instant(query, limit=5))

    if not all_results:
        return "No results found. Try a different query."

    # Deduplicate by URL
    seen = set()
    unique = []
    for r in all_results:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique.append(r)

    # Format output
    lines = []
    for i, r in enumerate(unique[:max_results]):
        lines.append(f"{i+1}. [{r['source']}] {r['title']}")
        lines.append(f"   {r['url']}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet'][:150]}")
        lines.append("")

    return "\n".join(lines)


web_search_tool = {
    "name": "web_search",
    "description": "Search the internet for real-time info. Uses OpenSERP (Bing, Yandex, Google, DuckDuckGo) with Wikipedia fallback. No API key needed. Returns titles, URLs, and snippets.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search terms"
            },
            "max_results": {
                "type": "integer",
                "default": 10
            }
        },
        "required": ["query"]
    },
    "handler": web_search_handler
}
