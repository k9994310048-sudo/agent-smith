#!/usr/bin/env python3
"""
Agent Smith v4.2 — Master Control Program.
Single-process async core. High reliability.
"""
import asyncio
from agents.logging_config import setup_json_logging, get_logger
import logging
import sys
import os
import threading
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# Load .env before anything else
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)
    print(f'Loaded .env from {env_path}')


# Logging setup
DATA_DIR = os.path.expanduser("~/.agent-smith")
os.makedirs(DATA_DIR, exist_ok=True)

log_formatter = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
log_file = os.path.join(DATA_DIR, "system.log")

file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
console_handler.setLevel(logging.INFO)

logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
logger = get_logger("master-core")
setup_json_logging("INFO")

PROJECT_ROOT = "/home/mac/.agent-smith"

async def main():
    try:
        logger.info("Initializing Agent Smith AGI v4.2...")

        # 1. Cleanup
        os.system("fuser -k 8766/tcp 8767/tcp 8768/tcp 2>/dev/null || true")

        # 2. Infrastructure (IKKF API + Web UI)
        logger.info("🧠 Starting IKKF API (8766)...")
        subprocess.Popen(["bash", "start-ikkf-api.sh"], cwd=PROJECT_ROOT, stdout=subprocess.DEVNULL, start_new_session=True)
        logger.info("📡 Starting Web UI (8767)...")
        subprocess.Popen(["bash", "start-ikkf-web.sh"], cwd=PROJECT_ROOT, stdout=subprocess.DEVNULL, start_new_session=True)

        # 3. Agent Initialization
        from agents.smith import AgentSmith
        agent = AgentSmith()
        await agent.initialize()

        # 3.5 Self-Repair Check
        logger.info("🔧 Running self-diagnostics...")
        repair_result = agent.self_repair.run_diagnostics()
        if repair_result["healthy"]:
            logger.info("✅ All systems healthy")
        else:
            logger.warning(f"⚠️ Self-repair actions: {len(repair_result["actions"])}")
            for action in repair_result["actions"]:
                logger.warning(f"  → {action}")

        # 4. Core Lifecycle
        from agents.core_system import get_core
        core = get_core(agent)
        asyncio.create_task(core.cognitive_loop())

        # 5. Dashboard (8768)
        from web.dashboard import run_dashboard
        threading.Thread(target=run_dashboard, args=(agent, 8768), daemon=True).start()

        # 6. Telegram Bot
        from integrations.telegram import TelegramBot
        bot = TelegramBot(token=agent.config["telegram"]["token"])
# 7. Morning delivery check (периодическая проверка каждый час)
        from datetime import datetime as _dt
        last_morning_check = None
        async def _morning_check_loop():
            nonlocal last_morning_check
            while True:
                await asyncio.sleep(3600)  # проверка каждый час
                now = _dt.now()
                if now.hour == 7 and last_morning_check != now.day:
                    last_morning_check = now.day
                    try:
                        await agent.send_morning_delivery()
                    except Exception as e:
                        logger.error(f"Morning delivery error: {e}")
        asyncio.create_task(_morning_check_loop())

        logger.info("✅ SYSTEM FULLY OPERATIONAL. Monitoring for messages.")
        await bot.process_updates(agent)

    except Exception as e:
        logger.critical(f"SYSTEM CRASH: {e}", exc_info=True)
        # Final cleanup attempt
        os.system("fuser -k 8766/tcp 8767/tcp 8768/tcp 2>/dev/null")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Halted.")
