"""
Lightweight Dashboard для Agent Smith на FastAPI.
Health-checks: /health, /ready, /deep
"""
import os
import sys
import shutil
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = FastAPI(title="Agent Smith Dashboard")

agent_instance = None

def set_agent(agent):
    global agent_instance
    agent_instance = agent

@app.get("/health")
async def health():
    return JSONResponse({"status": "alive", "service": "agent-smith"})

@app.get("/ready")
async def ready():
    ok = agent_instance is not None
    return JSONResponse({
        "status": "ready" if ok else "not_ready",
        "agent_initialized": ok
    }, status_code=200 if ok else 503)

@app.get("/deep")
async def deep():
    checks = {}
    try:
        stat = shutil.disk_usage("/")
        free_pct = stat.free / stat.total * 100
        checks["disk"] = {"ok": free_pct > 10, "free_pct": round(free_pct, 1)}
    except Exception as e:
        checks["disk"] = {"ok": False, "error": str(e)}

    checks["agent"] = {"ok": agent_instance is not None}
    if agent_instance:
        try:
            status = agent_instance.get_status()
            checks["llm"] = {"ok": True, "mode": status.get("llm_mode", "unknown")}
        except Exception as e:
            checks["llm"] = {"ok": False, "error": str(e)}
    else:
        checks["llm"] = {"ok": False, "error": "agent not initialized"}

    overall = all(c.get("ok", False) for c in checks.values())
    return JSONResponse({
        "status": "healthy" if overall else "degraded",
        "checks": checks
    }, status_code=200 if overall else 503)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if not agent_instance:
        return "Агент не инициализирован."

    status = agent_instance.get_status()
    facts = agent_instance.memory.get('facts', [])[-10:]
    facts_str = '\n'.join(facts) if facts else 'Память пуста'

    html = f"""
    <html>
    <head>
        <title>Agent Smith Dashboard</title>
        <style>
            body {{ font-family: sans-serif; background: #121212; color: #e0e0e0; padding: 20px; }}
            .card {{ background: #1e1e1e; padding: 20px; border-radius: 8px; margin-bottom: 20px; border: 1px solid #333; }}
            h1 {{ color: #00e5ff; }}
            h2 {{ color: #00e5ff; font-size: 1.2em; }}
            .stat-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }}
            .stat-item {{ background: #252525; padding: 15px; border-radius: 4px; text-align: center; }}
            .stat-val {{ font-size: 1.5em; font-weight: bold; color: #fff; }}
            .stat-label {{ color: #888; font-size: 0.8em; text-transform: uppercase; }}
            pre {{ background: #000; padding: 10px; border-radius: 4px; overflow-x: auto; color: #0f0; font-size: 0.9em; }}
            a {{ color: #00e5ff; }}
        </style>
    </head>
    <body>
        <h1>Agent Smith Dashboard</h1>

        <div class="card">
            <h2>Статус системы</h2>
            <div class="stat-grid">
                <div class="stat-item">
                    <div class="stat-val">{status['llm_mode']}</div>
                    <div class="stat-label">LLM Режим</div>
                </div>
                <div class="stat-item">
                    <div class="stat-val">{status['memory_facts']}</div>
                    <div class="stat-label">Фактов в памяти</div>
                </div>
                <div class="stat-item">
                    <div class="stat-val">{status['skills_loaded']}</div>
                    <div class="stat-label">Навыков</div>
                </div>
                <div class="stat-item">
                    <div class="stat-val">{'ON' if status['config']['uses_api'] else 'OFF'}</div>
                    <div class="stat-label">Внешний API</div>
                </div>
            </div>
        </div>

        <div class="card">
            <h2>Последние факты</h2>
            <pre>{facts_str}</pre>
        </div>

        <div style="text-align: center; color: #444; font-size: 0.8em;">
            Health: <a href="/health">/health</a> | <a href="/ready">/ready</a> | <a href="/deep">/deep</a>
        </div>
    </body>
    </html>
    """
    return html

def run_dashboard(agent, port=8768):
    set_agent(agent)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="error")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8768)
