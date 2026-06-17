"""
Web Account Proxy Manager
Manages free AI web accounts via ForgetMeAI proxies.
Supports: DeepSeek, GLM/Kimi, Qwen
Each proxy runs as a subprocess on its own port.
"""

import subprocess
import os
import json
import logging
import time
import urllib.request
import urllib.error

logger = logging.getLogger("web-proxy")

PROXY_DIR = "/home/mac/.agent-smith/web-proxy"

PROXIES = {
    "deepseek": {
        "name": "FreeDeepseekAPI",
        "port": 9655,
        "dir": os.path.join(PROXY_DIR, "FreeDeepseekAPI"),
        "entry": "server.js",
        "model": "deepseek-chat",
        "type": "node",
    },
    "glm": {
        "name": "FreeGLMKimiAPI",
        "port": 9766,
        "dir": os.path.join(PROXY_DIR, "FreeGLMKimiAPI"),
        "entry": "src/server.js",
        "model": "glm-4-plus",
        "type": "node",
    },
    "qwen": {
        "name": "FreeQwenApi",
        "port": 3264,
        "dir": os.path.join(PROXY_DIR, "FreeQwenApi"),
        "entry": "main.py",
        "model": "qwen-plus",
        "type": "python",
    },
}

_running = {}


def _is_port_open(port):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=2)
        return True
    except:
        return False


def install_deps(proxy_key):
    """Install npm/pip dependencies for a proxy."""
    p = PROXIES[proxy_key]
    if p["type"] == "node":
        r = subprocess.run(
            ["npm", "install", "--production"],
            cwd=p["dir"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return r.returncode == 0, r.stderr[:200] if r.returncode != 0 else ""
    else:
        r = subprocess.run(
            ["pip3", "install", "-r", "requirements.txt"],
            cwd=p["dir"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return r.returncode == 0, r.stderr[:200] if r.returncode != 0 else ""


def start_proxy(proxy_key):
    """Start a proxy server as background process."""
    if proxy_key not in PROXIES:
        return False, f"Unknown proxy: {proxy_key}"

    if proxy_key in _running:
        pid = _running[proxy_key]
        try:
            os.kill(pid, 0)
            return True, f"{proxy_key} already running (PID {pid})"
        except ProcessLookupError:
            pass
    elif _is_port_open(PROXIES[proxy_key]["port"]):
        return True, f"{proxy_key} already listening on port {PROXIES[proxy_key]['port']}"

    p = PROXIES[proxy_key]
    try:
        if p["type"] == "node":
            cmd = ["node", p["entry"]]
        else:
            cmd = ["python3", p["entry"]]

        log_file = os.path.join("/tmp", f"proxy_{proxy_key}.log")
        with open(log_file, "w") as lf:
            proc = subprocess.Popen(
                cmd,
                cwd=p["dir"],
                stdout=lf,
                stderr=lf,
                start_new_session=True,
            )

        for _ in range(10):
            time.sleep(1)
            if _is_port_open(p["port"]):
                _running[proxy_key] = proc.pid
                logger.info(f"Started {proxy_key} proxy on port {p['port']} (PID {proc.pid})")
                return True, f"Started {proxy_key} on :{p['port']}"

        return False, f"{proxy_key} didn't start within 10s. Check {log_file}"

    except Exception as e:
        return False, str(e)


def stop_proxy(proxy_key):
    """Stop a running proxy."""
    if proxy_key in _running:
        try:
            os.kill(_running[proxy_key], 15)
            del _running[proxy_key]
            return True, f"Stopped {proxy_key}"
        except ProcessLookupError:
            del _running[proxy_key]
            return True, f"{proxy_key} was already dead"

    p = PROXIES.get(proxy_key)
    if p:
        os.system(f"fuser -k {p['port']}/tcp 2>/dev/null")
        return True, f"Killed process on port {p['port']}"

    return False, f"Unknown proxy: {proxy_key}"


def stop_all():
    """Stop all running proxies."""
    results = {}
    for key in list(_running.keys()):
        ok, msg = stop_proxy(key)
        results[key] = msg
    return results


def get_status():
    """Get status of all proxies."""
    status = {}
    for key, p in PROXIES.items():
        running = _is_port_open(p["port"])
        pid = _running.get(key)
        status[key] = {
            "name": p["name"],
            "port": p["port"],
            "running": running,
            "pid": pid,
            "model": p["model"],
            "dir": p["dir"],
        }
    return status


def get_available_models():
    """Query all running proxies for their models."""
    models = []
    for key, p in PROXIES.items():
        if _is_port_open(p["port"]):
            try:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{p['port']}/v1/models",
                    headers={"Authorization": "Bearer free"},
                )
                resp = urllib.request.urlopen(req, timeout=5)
                data = json.loads(resp.read())
                for m in data.get("data", []):
                    models.append({
                        "id": m["id"],
                        "proxy": key,
                        "port": p["port"],
                    })
            except Exception as e:
                logger.warning(f"Failed to get models from {key}: {e}")
    return models


class WebProxyClient:
    """
    OpenAI-compatible client that routes through web account proxies.
    Usage:
        client = WebProxyClient(proxy="deepseek")
        response = await client.chat(messages=[...])
    """

    def __init__(self, proxy="deepseek"):
        self.proxy = proxy
        self.config = PROXIES[proxy]
        self.base_url = f"http://127.0.0.1:{self.config['port']}/v1"

    async def chat(self, messages, model=None, max_tokens=2048, temperature=0.7):
        """Send chat completion request through proxy."""
        import httpx

        payload = {
            "model": model or self.config["model"],
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={
                    "Authorization": "Bearer free",
                    "Content-Type": "application/json",
                },
            )
            return resp.json()
