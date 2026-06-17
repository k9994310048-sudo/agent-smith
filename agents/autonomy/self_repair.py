"""
Self-Repair Module v1.0 — Agent Smith Self-Healing System.
Monitors health and auto-recovers from failures.
Rule: "Do no harm" — verify before acting, rollback on failure.
"""
import logging
import os
import subprocess
import shutil
import time
import json
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("self-repair")
PROJECT_ROOT = "/home/mac/.agent-smith"

# Service definitions: name -> (port, start_cmd, health_check)
SERVICES = {
    "ikkf_api": {
        "port": 8766,
        "start_cmd": ["bash", "start-ikkf-api.sh"],
        "health_url": "http://127.0.0.1:8766/health",
        "critical": True,
    },
    "ikkf_web": {
        "port": 8767,
        "start_cmd": ["bash", "start-ikkf-web.sh"],
        "health_url": "http://127.0.0.1:8767",
        "critical": False,
    },
    "dashboard": {
        "port": 8768,
        "start_cmd": None,  # started by main.py
        "health_url": "http://127.0.0.1:8768/health",
        "critical": False,
    },
    "deepseek_r1": {
        "port": 8081,
        "start_cmd": None,  # started externally
        "health_url": "http://127.0.0.1:8081/health",
        "critical": False,
    },
    "qwen_05b": {
        "port": 8080,
        "start_cmd": None,
        "health_url": "http://127.0.0.1:8080/health",
        "critical": False,
    },
}


def check_port(port):
    """Check if a port is open."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        result = s.connect_ex(("127.0.0.1", port))
        s.close()
        return result == 0
    except:
        return False


def check_disk_space():
    """Check disk space. Returns (ok, free_pct, message)."""
    try:
        stat = shutil.disk_usage("/")
        free_pct = (stat.free / stat.total) * 100
        if free_pct < 5:
            return False, free_pct, f"CRITICAL: Disk {free_pct:.1f}% free"
        elif free_pct < 10:
            return False, free_pct, f"WARNING: Disk {free_pct:.1f}% free"
        return True, free_pct, f"OK: Disk {free_pct:.1f}% free"
    except Exception as e:
        return False, 0, f"Error checking disk: {e}"


def check_ram():
    """Check available RAM. Returns (ok, free_gb, message)."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    free_gb = kb / 1024 / 1024
                    if free_gb < 0.5:
                        return False, free_gb, f"CRITICAL: RAM {free_gb:.1f} GB free"
                    elif free_gb < 1.0:
                        return False, free_gb, f"WARNING: RAM {free_gb:.1f} GB free"
                    return True, free_gb, f"OK: RAM {free_gb:.1f} GB free"
    except Exception as e:
        return False, 0, f"Error checking RAM: {e}"
    return True, 4.0, "OK: RAM check skipped"


def check_db_integrity():
    """Check SQLite database integrity."""
    db_path = os.path.join(PROJECT_ROOT, "data", "graph.db")
    if not os.path.exists(db_path):
        return False, "Database file missing"
    try:
        import sqlite3
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        if result[0] == "ok":
            size_mb = os.path.getsize(db_path) / 1024 / 1024
            return True, f"OK ({size_mb:.1f} MB)"
        return False, f"Integrity: {result[0]}"
    except Exception as e:
        return False, f"DB check error: {e}"


def kill_port(port):
    """Kill process on port."""
    try:
        subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True, timeout=5)
        time.sleep(1)
        return True
    except:
        return False


def start_service(name, service):
    """Start a service."""
    if service["start_cmd"] is None:
        return False, f"Cannot auto-start {name} (external)"
    try:
        subprocess.Popen(
            service["start_cmd"],
            cwd=PROJECT_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        time.sleep(3)
        if check_port(service["port"]):
            return True, f"Started {name} on port {service["port"]}"
        return False, f"Failed to start {name}"
    except Exception as e:
        return False, f"Error starting {name}: {e}"


def cleanup_logs():
    """Clean up old log files to free disk space."""
    freed = 0
    log_files = [
        os.path.join(PROJECT_ROOT, "system.log"),
        os.path.join(PROJECT_ROOT, "data", "dream.log"),
        os.path.join(PROJECT_ROOT, "ikkf-auto-save.log"),
        os.path.join(PROJECT_ROOT, "ikkf-rule-capture.log"),
    ]
    for log_file in log_files:
        if os.path.exists(log_file):
            size = os.path.getsize(log_file)
            if size > 10 * 1024 * 1024:  # > 10 MB
                # Truncate to last 1000 lines
                try:
                    with open(log_file, "r") as f:
                        lines = f.readlines()
                    with open(log_file, "w") as f:
                        f.writelines(lines[-1000:])
                    freed += size - os.path.getsize(log_file)
                except:
                    pass
    return freed


class SelfRepair:
    """Self-healing system for Agent Smith."""

    def __init__(self, agent):
        self.agent = agent
        self.repair_log = []
        self.last_check = 0
        self.check_interval = 300  # 5 minutes

    def diagnose(self):
        """Run full system diagnosis. Returns dict of results."""
        results = {
            "timestamp": datetime.utcnow().isoformat(),
            "services": {},
            "system": {},
            "overall": "healthy",
        }

        # Check services
        for name, service in SERVICES.items():
            running = check_port(service["port"])
            results["services"][name] = {
                "running": running,
                "port": service["port"],
                "critical": service["critical"],
            }
            if not running and service["critical"]:
                results["overall"] = "degraded"

        # Check system
        disk_ok, disk_pct, disk_msg = check_disk_space()
        ram_ok, ram_gb, ram_msg = check_ram()
        db_ok, db_msg = check_db_integrity()

        results["system"] = {
            "disk": {"ok": disk_ok, "message": disk_msg},
            "ram": {"ok": ram_ok, "message": ram_msg},
            "db": {"ok": db_ok, "message": db_msg},
        }

        if not disk_ok or not ram_ok or not db_ok:
            results["overall"] = "critical"

        return results

    def heal(self, diagnosis=None):
        """Auto-heal based on diagnosis. Returns list of actions taken."""
        if diagnosis is None:
            diagnosis = self.diagnose()

        actions = []

        # Heal critical services
        for name, status in diagnosis["services"].items():
            if not status["running"] and status["critical"]:
                service = SERVICES[name]
                if service["start_cmd"]:
                    # Kill port first, then restart
                    kill_port(service["port"])
                    ok, msg = start_service(name, service)
                    actions.append({"action": "restart", "service": name, "success": ok, "message": msg})
                    logger.warning(f"Self-repair: {msg}")

        # Heal disk space
        disk_info = diagnosis["system"]["disk"]
        if not disk_info["ok"]:
            freed = cleanup_logs()
            if freed > 0:
                actions.append({"action": "cleanup_logs", "freed_bytes": freed})
                logger.warning(f"Self-repair: Cleaned up {freed / 1024 / 1024:.1f} MB of logs")

            # Check if still critical
            disk_ok, disk_pct, _ = check_disk_space()
            if not disk_ok:
                actions.append({"action": "disk_critical", "message": "Manual intervention needed"})
                logger.error("Self-repair: Disk still critical after cleanup!")

        # Heal DB
        db_info = diagnosis["system"]["db"]
        if not db_info["ok"]:
            # Try to restore from backup
            backup_dir = os.path.join(PROJECT_ROOT, "backups")
            db_path = os.path.join(PROJECT_ROOT, "data", "graph.db")
            if os.path.exists(backup_dir):
                backups = sorted(Path(backup_dir).glob("graph-*.db"), reverse=True)
                if backups:
                    try:
                        # Verify backup integrity
                        import sqlite3
                        conn = sqlite3.connect(str(backups[0]))
                        result = conn.execute("PRAGMA integrity_check").fetchone()
                        conn.close()
                        if result[0] == "ok":
                            # Backup current (corrupted) DB
                            corrupt_path = db_path + ".corrupt." + datetime.utcnow().strftime("%Y%m%d%H%M%S")
                            shutil.move(db_path, corrupt_path)
                            shutil.copy2(str(backups[0]), db_path)
                            actions.append({"action": "db_restore", "from": str(backups[0])})
                            logger.warning(f"Self-repair: Restored DB from {backups[0]}")
                    except Exception as e:
                        actions.append({"action": "db_restore_failed", "error": str(e)})
                        logger.error(f"Self-repair: DB restore failed: {e}")

        # Log repairs
        if actions:
            self.repair_log.append({
                "timestamp": datetime.utcnow().isoformat(),
                "actions": actions,
            })
            # Keep only last 50 repairs
            self.repair_log = self.repair_log[-50:]

        return actions

    def run_diagnostics(self):
        """Run diagnostics and auto-heal if needed. Returns summary."""
        diagnosis = self.diagnose()
        actions = []

        if diagnosis["overall"] != "healthy":
            logger.warning(f"Self-repair: System {diagnosis["overall"]}, running healing...")
            actions = self.heal(diagnosis)

        self.last_check = time.time()
        return {
            "diagnosis": diagnosis,
            "actions": actions,
            "healthy": diagnosis["overall"] == "healthy" and len(actions) == 0,
        }
