#!/usr/bin/env python3
"""
IKKF Debug Tool — наблюдаемость без веб-UI.

Usage:
    python3 ikkf_debug.py search "query"     — показать весь путь поиска
    python3 ikkf_debug.py rag "query"        — показать GraphRAG пайплайн
    python3 ikkf_debug.py consolidate-log    — показать последний лог консолидации
    python3 ikkf_debug.py stats              — статистика графа
    python3 ikkf_debug.py node <id>          — детали узла с контекстом и связями
"""

import sys
import os
import json
import urllib.request
import urllib.parse
from datetime import datetime

IKKF_API = "http://127.0.0.1:8766"


def api_get(path, params=None):
    url = f"{IKKF_API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


def api_post(path, data):
    url = f"{IKKF_API}{path}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


def debug_search(query, limit=5):
    """Показать детали гибридного поиска."""
    print(f"=== IKKF Debug: Search ===")
    print(f"Query: {query}")
    print()

    r = api_get("/search/hybrid", {"q": query, "limit": limit, "debug": "true"})
    if "error" in r:
        print(f"ERROR: {r['error']}")
        return

    debug = r.get("debug", {})
    print(f"FTS5 matches: {debug.get('fts_count', 0)}")
    print(f"Vector matches: {debug.get('vec_count', 0)}")
    print(f"Combined: {debug.get('combined_count', 0)}")
    print(f"Returned: {r['count']}")
    print()

    if debug.get("fts_top"):
        print("--- FTS5 Top ---")
        for node_id, score in debug["fts_top"][:3]:
            print(f"  {score:.4f} | {node_id[:8]}...")

    if debug.get("vec_top"):
        print("--- Vector Top ---")
        for node_id, score in debug["vec_top"][:3]:
            print(f"  {score:.4f} | {node_id[:8]}...")

    print()
    print("--- Results ---")
    for i, item in enumerate(r.get("results", [])[:limit], 1):
        print(f"{i}. [{item['node_type']}] score={item['score']:.4f} (fts={item['fts_score']:.4f}, vec={item['vec_score']:.4f})")
        print(f"   {item['content'][:150]}")
        print()


def debug_rag(query, limit=5):
    """Показать детали GraphRAG пайплайна."""
    print(f"=== IKKF Debug: GraphRAG ===")
    print(f"Query: {query}")
    print()

    r = api_post("/rag", {"query": query, "limit": limit, "debug": True})
    if "error" in r:
        print(f"ERROR: {r['error']}")
        return

    stats = r.get("stats", {})
    print(f"Seed nodes: {stats.get('seeds_found', 0)}")
    print(f"Expanded: {stats.get('expanded_count', 0)}")
    print(f"Final: {stats.get('final_count', 0)}")
    print(f"Context length: {len(r.get('context_text', ''))} chars")
    print()

    nodes = r.get("context_nodes", [])
    if nodes:
        print("--- Context Nodes ---")
        for i, n in enumerate(nodes, 1):
            ctx = n.get("context", {})
            dims = {k: v for k, v in ctx.items() if v}
            dim_str = f" dims={dims}" if dims else ""
            print(f"{i}. [{n.get('node_type', '?')}] imp={n.get('importance', '?')}{dim_str}")
            print(f"   {str(n.get('content', ''))[:150]}")
            print()


def show_consolidate_log():
    """Показать последний лог консолидации."""
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    if not os.path.exists(log_dir):
        print("No logs directory. Run consolidate.sh first.")
        return

    logs = sorted([f for f in os.listdir(log_dir) if f.startswith("consolidate-")], reverse=True)
    if not logs:
        print("No consolidation logs found.")
        return

    log_file = os.path.join(log_dir, logs[0])
    print(f"=== Last Consolidation Log: {logs[0]} ===")
    print()

    with open(log_file) as f:
        content = f.read()
        # Show last 50 lines
        lines = content.strip().split("\n")
        if len(lines) > 50:
            print(f"... ({len(lines) - 50} lines omitted) ...")
            print()
        for line in lines[-50:]:
            print(line)


def show_stats():
    """Показать статистику графа."""
    r = api_get("/stats")
    if "error" in r:
        print(f"ERROR: {r['error']}")
        return

    print(f"=== IKKF Graph Stats ===")
    print()
    print(f"Nodes: {r.get('nodes_total', 0)} (active: {r.get('nodes_active', 0)})")
    print(f"Edges: {r.get('edges_total', 0)}")
    print(f"Chunks: {r.get('chunks_total', 0)}")
    print(f"Documents: {r.get('documents_total', 0)}")
    print(f"Projects: {r.get('projects_total', 0)}")
    print(f"DB size: {r.get('db_size_mb', 0)} MB")
    print()

    by_type = r.get("by_type", {})
    if by_type:
        print("--- By Type ---")
        for t, c in sorted(by_type.items(), key=lambda x: x[1], reverse=True):
            print(f"  {t}: {c}")

    by_project = r.get("by_project", {})
    if by_project:
        print()
        print("--- By Project ---")
        for p, c in sorted(by_project.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {p}: {c}")


def show_node(node_id):
    """Показать детали узла."""
    r = api_get(f"/node/{node_id}")
    if "error" in r:
        print(f"ERROR: {r['error']}")
        return

    print(f"=== Node: {node_id[:8]}... ===")
    print(f"Type: {r.get('node_type', '?')}")
    print(f"Importance: {r.get('importance', '?')}")
    print(f"Status: {r.get('status', '?')}")
    print(f"Access count: {r.get('access_count', 0)}")
    print(f"Created: {r.get('created_at', '?')}")
    print()

    ctx = r.get("context", {})
    if ctx:
        print("--- Context Dimensions ---")
        for dim in ["temporal", "spatial", "social", "emotional", "semantic"]:
            val = ctx.get(dim)
            if val:
                print(f"  {dim}: {val}")
        print()

    print(f"Content:")
    print(f"  {r.get('content', '')[:500]}")
    print()

    # Show edges
    edges = api_get(f"/neighbors/{node_id}")
    if edges and not edges.get("error"):
        print(f"--- Connections ({len(edges.get('edges', []))}) ---")
        for e in edges.get("edges", [])[:10]:
            direction = "→" if e.get("source_id") == node_id else "←"
            print(f"  {direction} [{e.get('edge_type', '?')}] weight={e.get('weight', '?')} | {e.get('target_content', e.get('source_content', ''))[:80]}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "search":
        if len(sys.argv) < 3:
            print("Usage: ikkf_debug.py search <query>")
            sys.exit(1)
        debug_search(" ".join(sys.argv[2:]))

    elif cmd == "rag":
        if len(sys.argv) < 3:
            print("Usage: ikkf_debug.py rag <query>")
            sys.exit(1)
        debug_rag(" ".join(sys.argv[2:]))

    elif cmd == "consolidate-log":
        show_consolidate_log()

    elif cmd == "stats":
        show_stats()

    elif cmd == "node":
        if len(sys.argv) < 3:
            print("Usage: ikkf_debug.py node <node_id>")
            sys.exit(1)
        show_node(sys.argv[2])

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)
