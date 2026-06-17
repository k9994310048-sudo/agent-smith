"""
System Tools v4.1.1 — Fixed schema structure.
"""
import logging
import subprocess
import os

logger = logging.getLogger("system-tools")
PROJECT_ROOT = "/home/mac/.agent-smith"

def shell_exec_handler(command: str, timeout: int = 30) -> str:
    forbidden = ["rm ", "sudo ", "apt ", "pip install", "git clone", "wget ", "curl -O", "chmod ", "chown "]
    if any(t in command for t in forbidden): return "❌ SECURITY ERROR: Forbidden command."
    if ">" in command and "2>/dev/null" not in command: return "❌ SECURITY ERROR: Writing prohibited."
    try:
        command = command.replace("/root/.agent-smith", PROJECT_ROOT)
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
        return (result.stdout + result.stderr).strip()[:2000]
    except Exception as e: return f"❌ Error: {e}"

def file_read_handler(file_path: str) -> str:
    try:
        clean = file_path.replace("/root/.agent-smith", PROJECT_ROOT)
        if not clean.startswith("/"): clean = os.path.join(PROJECT_ROOT, clean)
        abs_p = os.path.abspath(os.path.expanduser(clean))
        if not abs_p.startswith(PROJECT_ROOT): return "❌ Access Denied."
        with open(abs_p, 'r', encoding='utf-8') as f:
            c = f.read()
            return c[:1500] + ("\n...[TRUNCATED]" if len(c) > 1500 else "")
    except Exception as e: return f"❌ Read Error: {e}"

def project_overview_handler() -> str:
    try:
        overview = f"📂 **Project ({PROJECT_ROOT}):**\n"
        for entry in sorted(os.listdir(PROJECT_ROOT)):
            if entry.startswith('.') or entry in ['venv', '__pycache__']: continue
            overview += f"{'📁' if os.path.isdir(os.path.join(PROJECT_ROOT, entry)) else '📄'} {entry}\n"
        return overview
    except Exception as e: return f"❌ Error: {e}"

# Tool Definitions (OpenAI Format)
shell_exec_tool = {
    "name": "shell_exec",
    "description": "Run bash analysis commands.",
    "parameters": {
        "type": "object",
        "properties": {"command": {"type": "string"}},
        "required": ["command"]
    },
    "handler": shell_exec_handler
}

file_read_tool = {
    "name": "file_read",
    "description": "Read a project file.",
    "parameters": {
        "type": "object",
        "properties": {"file_path": {"type": "string"}},
        "required": ["file_path"]
    },
    "handler": file_read_handler
}

project_overview_tool = {
    "name": "project_overview",
    "description": "View project file tree.",
    "parameters": {"type": "object", "properties": {}, "required": []},
    "handler": project_overview_handler
}

def get_system_stats_handler() -> str:
    """Return real system stats: uptime, load, RAM, disk, CPU."""
    import subprocess, os
    lines = []
    # Uptime
    try:
        r = subprocess.run("uptime -p", shell=True, capture_output=True, text=True, timeout=5)
        lines.append("Uptime: " + r.stdout.strip())
    except:
        pass
    # Load average
    try:
        load = os.getloadavg()
        ncpu = os.cpu_count() or 2
        lines.append(f"Load: {load[0]:.2f} {load[1]:.2f} {load[2]:.2f} ({ncpu} cores)")
    except:
        pass
    # RAM
    try:
        with open("/proc/meminfo") as f:
            meminfo = f.read()
        total = avail = 0
        for line in meminfo.split("\n"):
            if line.startswith("MemTotal:"):
                total = int(line.split()[1])
            elif line.startswith("MemAvailable:"):
                avail = int(line.split()[1])
        if total:
            used_pct = (1 - avail / total) * 100
            lines.append(f"RAM: {avail/1024/1024:.1f}GB free / {total/1024/1024:.1f}GB total ({used_pct:.0f}% used)")
    except:
        pass
    # Disk
    try:
        stat = os.statvfs("/")
        free_gb = stat.f_bavail * stat.f_frsize / 1024 / 1024 / 1024
        total_gb = stat.f_blocks * stat.f_frsize / 1024 / 1024 / 1024
        used_pct = (1 - stat.f_bavail / stat.f_blocks) * 100
        lines.append(f"Disk: {free_gb:.1f}GB free / {total_gb:.1f}GB total ({used_pct:.0f}% used)")
    except:
        pass
    # CPU temp if available
    try:
        r = subprocess.run("cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null", shell=True, capture_output=True, text=True, timeout=3)
        temp = int(r.stdout.strip()) / 1000
        lines.append(f"CPU temp: {temp:.0f}°C")
    except:
        pass
    return "\n".join(lines) if lines else "System stats unavailable"

get_system_stats_tool = {
    "name": "get_system_stats",
    "description": "Check system resources: uptime, CPU load, RAM, disk, temperature.",
    "parameters": {"type": "object", "properties": {}, "required": []},
    "handler": get_system_stats_handler
}
