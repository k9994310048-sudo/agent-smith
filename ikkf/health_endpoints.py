"""
Health check endpoints for IKKF API.
Provides /health, /ready, and /deep endpoints.
"""
import logging
import time
from datetime import datetime

logger = logging.getLogger("health-check")

# Track startup time
_START_TIME = time.time()

def get_health_status():
    """Basic liveness check."""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "uptime_seconds": round(time.time() - _START_TIME, 1),
    }

def get_readiness_status():
    """Readiness check - verify all dependencies."""
    checks = {}
    all_ok = True

    # Check IKKF graph DB
    try:
        from ikkf.graph import Graph
        g = Graph("data/graph.db")
        node_count = g.count_nodes()
        checks["graph_db"] = {"ok": True, "nodes": node_count}
    except Exception as e:
        checks["graph_db"] = {"ok": False, "error": str(e)[:100]}
        all_ok = False

    return {
        "status": "ok" if all_ok else "degraded",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "checks": checks,
    }

def get_deep_health_status():
    """Deep health check - full system status."""
    import psutil
    import os

    status = get_readiness_status()

    # System resources
    status["system"] = {
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage("/").percent,
        "load_avg": list(os.getloadavg()),
    }

    # Agent status
    try:
        status["agent"] = {
            "pid": os.getpid(),
            "cwd": os.getcwd(),
            "python_version": os.sys.version[:50],
        }
    except:
        pass

    return status
