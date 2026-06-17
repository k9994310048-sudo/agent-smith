#!/usr/bin/env python3
"""
IKKF Tool — Mandatory memory layer for Hermes agent.

Usage:
    python3 ikkf_tool.py search "query"           — search IKKF, return context
    python3 ikkf_tool.py store "fact" [type]      — store fact to IKKF
    python3 ikkf_tool.py extract "text"           — extract facts from text
    python3 ikkf_tool.py health                   — check API health
    python3 ikkf_tool.py backfill                 — backfill missing embeddings
"""

import sys
import os
import json
import urllib.request
import urllib.parse
import re
import hashlib
from datetime import datetime

IKKF_API = os.environ.get("IKKF_API_URL", "http://127.0.0.1:8766")


def api_get(path, params=None):
    """GET request to IKKF API."""
    url = f"{IKKF_API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


def api_post(path, data):
    """POST request to IKKF API."""
    url = f"{IKKF_API}{path}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


def health():
    """Check IKKF API health."""
    r = api_get("/health")
    if r.get("status") == "ok":
        print("OK")
        return True
    else:
        print(f"FAIL: {r}")
        return False


def search(query, limit=5, method="hybrid"):
    """Search IKKF and return formatted context."""
    if method == "hybrid":
        r = api_get("/search/hybrid", {"q": query, "limit": limit})
    elif method == "vector":
        r = api_get("/search/vector", {"q": query, "limit": limit})
    elif method == "rag":
        r = api_post("/rag", {"query": query, "limit": limit})
    else:
        r = api_get("/search", {"q": query, "limit": limit})

    if "error" in r:
        print(f"ERROR: {r['error']}", file=sys.stderr)
        return None

    return r


def search_formatted(query, limit=5):
    """Search and return formatted text for prompt injection."""
    r = search(query, limit=limit, method="hybrid")
    if not r:
        return ""

    lines = []
    lines.append("=== IKKF Memory Context ===")
    lines.append("")

    results = r.get("results", [])
    if not results:
        return ""  # No matches — don't inject anything

    for i, item in enumerate(results, 1):
        node = item.get("node", item)
        node_type = node.get("node_type", "?")
        content = str(node.get("content", ""))[:300]
        score = item.get("vector_score", item.get("score", 0))
        lines.append(f"{i}. [{node_type}] (score={score:.3f}) {content}")

    lines.append("")
    lines.append(f"Total: {r.get('count', len(results))} results")
    return "\n".join(lines)


def store(content, node_type="fact", importance=0.5, tags=None, project="default"):
    """Store a fact in IKKF."""
    # Dedup: skip if too similar to recent stores
    r = api_post("/node", {
        "content": content,
        "node_type": node_type,
        "importance": importance,
        "tags": tags or [],
        "project": project,
    })
    if "error" in r:
        print(f"ERROR: {r['error']}", file=sys.stderr)
        return None
    return r


def extract_facts(text):
    """Extract key facts from text using heuristic rules."""
    facts = []

    # Pattern: "X is Y" / "X — Y"
    for m in re.finditer(r"([А-ЯA-Z][^.!?]{10,80})(?:—|—|:)\s*([^.!?]{10,100})", text):
        fact = f"{m.group(1).strip()} — {m.group(2).strip()}"
        if len(fact) > 20:
            facts.append(fact)

    # Pattern: "X работает / реализован / создан / обновлён"
    for m in re.finditer(r"([А-ЯA-Z][^.!?]*(?:работает|реализован|создан|обновлён|добавлен|удалён)[^.!?]{0,80})", text):
        fact = m.group(1).strip()
        if len(fact) > 15:
            facts.append(fact)

    # Pattern: "Bug fix: X" / "Issue: X"
    for m in re.finditer(r"(?:Bug|Issue|Fix|Task):\s*([^.!?]{10,100})", text, re.IGNORECASE):
        facts.append(f"Fix: {m.group(1).strip()}")

    # Dedup by hash
    seen = set()
    unique = []
    for f in facts:
        h = hashlib.md5(f.encode()).hexdigest()[:8]
        if h not in seen:
            seen.add(h)
            unique.append(f)

    return unique[:10]  # Max 10 facts


def backfill_embeddings():
    """Backfill missing embeddings for all nodes."""
    r = api_get("/nodes", {"limit": 1000})
    nodes = r.get("nodes", r.get("results", []))
    embedded = 0
    failed = 0
    for node in nodes:
        if node.get("embedding") is None:
            node_id = node.get("id")
            # Trigger re-embed via PUT
            api_post(f"/fill-context", {"node_id": node_id})
            embedded += 1
    print(f"Backfill: {embedded} nodes processed, {failed} failed")
    return embedded


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "health":
        health()

    elif cmd == "search":
        if len(sys.argv) < 3:
            print("Usage: ikkf_tool.py search <query> [limit]")
            sys.exit(1)
        query = sys.argv[2]
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        result = search_formatted(query, limit)
        if result:
            print(result)
        else:
            print("NO_RESULTS")

    elif cmd == "store":
        if len(sys.argv) < 3:
            print("Usage: ikkf_tool.py store <content> [node_type] [importance]")
            sys.exit(1)
        content = sys.argv[2]
        node_type = sys.argv[3] if len(sys.argv) > 3 else "fact"
        importance = float(sys.argv[4]) if len(sys.argv) > 4 else 0.5
        r = store(content, node_type, importance)
        if r and "node" in r:
            print(f"OK: {r['node']['id']}")
        else:
            print(f"FAIL: {r}")

    elif cmd == "extract":
        if len(sys.argv) < 3:
            print("Usage: ikkf_tool.py extract <text>")
            sys.exit(1)
        text = " ".join(sys.argv[2:])
        facts = extract_facts(text)
        for f in facts:
            print(f"- {f}")

    elif cmd == "backfill":
        backfill_embeddings()

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)
