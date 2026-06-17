#!/usr/bin/env python3
"""
IKKF Web UI — максимально простой.
Чистый HTML от FastAPI. Без JS фреймворков. Без Jinja2.

Запуск: python3 ikkf_web.py
URL: http://127.0.0.1:8767
"""

import os
import sys
import json
import urllib.request
import urllib.parse
import sqlite3
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

IKKF_API = "http://127.0.0.1:8766"
IKKF_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(IKKF_ROOT, "data", "graph.db")

app = FastAPI(title="IKKF Web UI")


def api_call(method, path, data=None, params=None):
    url = f"{IKKF_API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        if method == "GET":
            with urllib.request.urlopen(url, timeout=10) as r:
                return json.loads(r.read())
        else:
            body = json.dumps(data).encode()
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


def esc(s):
    """HTML escape."""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def base_header(page, stats):
    nodes = stats.get("nodes_total", "?")
    edges = stats.get("edges_total", "?")
    db_size = stats.get("db_size_mb", "?")
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>IKKF — Web UI</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#0d1117;color:#c9d1d9}}
.hd{{background:#161b22;padding:14px 24px;border-bottom:1px solid #30363d;display:flex;align-items:center;gap:14px}}
.hd h1{{font-size:17px;color:#58a6ff}}
.hd a{{color:#8b949e;text-decoration:none;font-size:13px;padding:4px 8px;border-radius:4px}}
.hd a:hover{{color:#58a6ff}}
.hd a.on{{color:#58a6ff;background:#1f6feb20;font-weight:600}}
.hd .info{{margin-left:auto;font-size:12px;color:#8b949e}}
.ct{{max-width:960px;margin:0 auto;padding:20px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:18px;margin-bottom:14px}}
.card h2{{font-size:15px;color:#f0f6fc;margin-bottom:10px}}
.sg{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px}}
.s{{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:10px;text-align:center}}
.s .v{{font-size:22px;font-weight:700;color:#58a6ff}}
.s .l{{font-size:10px;color:#8b949e;margin-top:3px;text-transform:uppercase}}
input[type=text]{{width:100%;background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:9px 12px;color:#c9d1d9;font-size:14px;outline:none}}
input:focus{{border-color:#58a6ff}}
.btn{{background:#238636;color:#fff;border:none;border-radius:6px;padding:9px 18px;font-size:13px;cursor:pointer}}
.btn:hover{{background:#2ea043}}
.btn.db{{background:#1f6feb}}
.r{{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:12px;margin-bottom:8px}}
.r .meta{{font-size:11px;color:#8b949e;margin-bottom:4px}}
.r .txt{{font-size:13px;line-height:1.5}}
.b{{display:inline-block;padding:1px 7px;border-radius:8px;font-size:10px;font-weight:600;margin-right:4px}}
.b.fact{{background:#1f6feb20;color:#58a6ff}}
.b.concept{{background:#a371f720;color:#a371f7}}
.b.action{{background:#23863620;color:#3fb950}}
.b.entity{{background:#d2992220;color:#d29922}}
.b.project{{background:#db6d2820;color:#db6d28}}
.b.event{{background:#f8514920;color:#f85149}}
.sc{{color:#58a6ff;font-weight:600}}
.debug{{margin-top:10px;padding-top:10px;border-top:1px solid #30363d}}
.debug .row{{display:flex;gap:8px;font-size:12px;margin-bottom:3px}}
.debug .r-l{{color:#8b949e;min-width:90px}}
.debug .r-v{{color:#58a6ff}}
.tab{{display:inline-block;padding:5px 12px;border-radius:4px;cursor:pointer;font-size:12px;color:#8b949e;margin-right:4px}}
.tab.on{{background:#1f6feb20;color:#58a6ff;font-weight:600}}
.bar{{height:14px;background:#21262d;border-radius:3px;overflow:hidden;display:inline-block;vertical-align:middle}}
.bar i{{display:block;height:100%;background:#58a6ff}}
</style></head><body>
<div class="hd">
<h1>IKKF</h1>
<a href="/" class="{'on' if page=='search' else ''}">Поиск</a>
<a href="/stats" class="{'on' if page=='stats' else ''}">Статистика</a>
<a href="/consolidation" class="{'on' if page=='consolidation' else ''}">Консолидация</a>
<span class="info">{nodes} nodes · {edges} edges · {db_size}MB</span>
</div>
<div class="ct">"""


def base_footer():
    return "</div></body></html>"


@app.get("/", response_class=HTMLResponse)
async def search_page(q: str = "", debug: str = ""):
    stats = api_call("GET", "/stats")
    html = base_header("search", stats)

    html += '<div class="card"><h2>Поиск</h2>'
    html += f'<form method="get" action="/" style="display:flex;gap:8px;margin-bottom:14px">'
    html += f'<input type="text" name="q" value="{esc(q)}" placeholder="Введите запрос..." autofocus>'
    html += '<button class="btn" type="submit">Найти</button>'
    html += '<button class="btn db" type="submit" name="debug" value="1">Debug (RAG)</button>'
    html += '</form>'

    if q:
        # Hybrid search
        hw = api_call("GET", "/search/hybrid", params={"q": q, "limit": 10})
        hw_results = hw.get("results", [])
        hw_count = hw.get("count", 0)

        if not debug:
            html += f'<h3 style="color:#58a6ff;margin-bottom:10px">Hybrid: {esc(hw_count)} results</h3>'
            for r in hw_results[:10]:
                nt = r.get("node_type", "?")
                sc = r.get("score", 0)
                fs = r.get("fts_score", 0)
                vs = r.get("vec_score", 0)
                html += '<div class="r">'
                html += f'<span class="b {nt}">{nt}</span>'
                html += f'<span class="sc">{sc:.3f}</span>'
                if fs > 0: html += f' <span style="color:#d29922;font-size:11px">fts:{fs:.3f}</span>'
                if vs > 0: html += f' <span style="color:#a371f7;font-size:11px">vec:{vs:.3f}</span>'
                html += f'<div class="txt">{esc(r.get("content","")[:300])}</div>'
                html += '</div>'
        else:
            # RAG debug
            rw = api_call("POST", "/rag", data={"query": q, "max_nodes": 10, "debug": True})
            rw_stats = rw.get("stats", {})
            rw_nodes = rw.get("context_nodes", [])
            rw_ctx_len = len(rw.get("context_text", ""))

            html += '<h3 style="color:#a371f7;margin-bottom:10px">GraphRAG Inspector</h3>'
            html += '<div class="debug">'
            html += f'<div class="row"><span class="r-l">Seeds</span><span class="r-v">{esc(rw_stats.get("seeds_found",0))}</span></div>'
            html += f'<div class="row"><span class="r-l">Expanded</span><span class="r-v">{esc(rw_stats.get("expanded_count",0))}</span></div>'
            html += f'<div class="row"><span class="r-l">Final</span><span class="r-v">{esc(rw_stats.get("final_count",0))}</span></div>'
            html += f'<div class="row"><span class="r-l">Context</span><span class="r-v">{esc(rw_ctx_len)} chars</span></div>'
            html += '</div>'

            for i, n in enumerate(rw_nodes[:10], 1):
                nt = n.get("node_type", "?")
                ctx = n.get("context", {})
                html += '<div class="r">'
                html += f'<span class="b {nt}">{nt}</span>'
                html += f' <span style="color:#8b949e;font-size:11px">#{esc(i)}</span>'
                dims = []
                for d in ["temporal", "social", "semantic", "emotional", "spatial"]:
                    if ctx.get(d):
                        dims.append(f'<span style="color:#d29922">{d[0]}:{esc(ctx[d])}</span>')
                if dims:
                    html += " " + " ".join(dims)
                html += f'<div class="txt">{esc(n.get("content","")[:300])}</div>'
                html += '</div>'

            # Also show hybrid results
            html += f'<h3 style="color:#58a6ff;margin:16px 0 10px">Also: Hybrid results ({esc(hw_count)})</h3>'
            for r in hw_results[:5]:
                nt = r.get("node_type", "?")
                html += '<div class="r">'
                html += f'<span class="b {nt}">{nt}</span>'
                html += f'<span class="sc">{r.get("score",0):.3f}</span>'
                html += f'<div class="txt">{esc(r.get("content","")[:200])}</div>'
                html += '</div>'
    else:
        html += '<p style="color:#8b949e;text-align:center;padding:30px">Введите запрос. Debug покажет GraphRAG пайплайн с контекстными измерениями.</p>'

    html += '</div>'
    html += base_footer()
    return HTMLResponse(html)


@app.get("/stats", response_class=HTMLResponse)
async def stats_page():
    stats = api_call("GET", "/stats")
    html = base_header("stats", stats)

    # Stats grid
    emb_count = 0
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM nodes WHERE embedding IS NOT NULL")
        emb_count = c.fetchone()[0]
        conn.close()
    except:
        pass
    emb_pct = round(emb_count / max(stats.get("nodes_total", 1), 1) * 100)

    html += '<div class="card"><h2>Статистика</h2><div class="sg">'
    for label, val in [
        ("Nodes", stats.get("nodes_total", 0)),
        ("Edges", stats.get("edges_total", 0)),
        ("FTS5 Chunks", stats.get("chunks_total", 0)),
        ("Projects", stats.get("projects_total", 0)),
        ("Embeddings", f"{emb_pct}%"),
        ("DB Size", f"{stats.get('db_size_mb', 0)}MB"),
    ]:
        html += f'<div class="s"><div class="v">{val}</div><div class="l">{label}</div></div>'
    html += '</div></div>'

    # By type
    html += '<div class="card"><h2>По типам</h2>'
    for t, c in sorted(stats.get("by_type", {}).items(), key=lambda x: x[1], reverse=True):
        html += f'<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #21262d">'
        html += f'<span><span class="b {t}">{t}</span></span><strong>{esc(c)}</strong></div>'
    html += '</div>'

    # By project
    html += '<div class="card"><h2>По проектам</h2>'
    for p, c in sorted(stats.get("by_project", {}).items(), key=lambda x: x[1], reverse=True)[:15]:
        html += f'<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #21262d">'
        html += f'<span style="color:#8b949e">{esc(p)}</span><strong>{esc(c)}</strong></div>'
    html += '</div>'

    # Timeline
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT DATE(created_at) as d, COUNT(*) as cnt FROM nodes GROUP BY d ORDER BY d")
        rows = c.fetchall()[-14:]
        conn.close()
        if rows:
            mx = max(r[1] for r in rows) or 1
            html += '<div class="card"><h2>Рост по дням</h2>'
            for d, cnt in rows:
                pct = round(cnt * 100 / mx)
                html += f'<div style="display:flex;align-items:center;gap:10px;padding:3px 0">'
                html += f'<span style="color:#8b949e;min-width:75px">{esc(d)}</span>'
                html += f'<div class="bar" style="flex:1"><i style="width:{pct}%"></i></div>'
                html += f'<span style="color:#8b949e;min-width:25px;text-align:right">{esc(cnt)}</span></div>'
            html += '</div>'
    except:
        pass

    html += base_footer()
    return HTMLResponse(html)


@app.get("/consolidation", response_class=HTMLResponse)
async def consolidation_page():
    stats = api_call("GET", "/stats")
    html = base_header("consolidation", stats)

    log_dir = os.path.join(IKKF_ROOT, "logs")
    html += '<div class="card"><h2>История консолидации</h2>'

    if os.path.exists(log_dir):
        log_files = sorted([f for f in os.listdir(log_dir) if f.startswith("consolidate-")], reverse=True)[:5]
        if log_files:
            for lf in log_files:
                path = os.path.join(log_dir, lf)
                sz = round(os.path.getsize(path) / 1024)
                mt = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
                with open(path) as fh:
                    content = fh.read()
                lines = content.strip().split("\n")
                preview = "\n".join(lines[-25:]) if len(lines) > 25 else content
                html += f'<div style="margin:10px 0">'
                html += f'<strong style="color:#58a6ff">{esc(lf)}</strong> '
                html += f'<span style="color:#8b949e;font-size:11px">({sz}KB) {mt}</span>'
                html += f'<div class="r"><div class="txt" style="font-family:monospace;font-size:11px;white-space:pre-wrap">{esc(preview[:800])}</div></div>'
                html += '</div>'
        else:
            html += '<p style="color:#8b949e">Логи не найдены.</p>'
    else:
        html += '<p style="color:#8b949e">Директория логов не найдена. Запустите <code>bash consolidate.sh</code></p>'

    html += '</div>'
    html += base_footer()
    return HTMLResponse(html)


if __name__ == "__main__":
    print("IKKF Web UI → http://127.0.0.1:8767")
    uvicorn.run(app, host="0.0.0.0", port=8767, log_level="warning")
