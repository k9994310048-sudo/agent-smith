"""
Agent Smith — Telegram Bot Runner
Запускает агента и слушает сообщения из Telegram.

Usage:
  python3 agents/bot_runner.py
"""

import json
import logging
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from agents.main import AgentSmithApp

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("bot_runner")

# ── Config ─────────────────────────────────────────────────────
TELEGRAM_TOKEN = "8958295263:AAH8HGwvxvqMEeuN6810pgAuqu0TBW7Dj7g"
CHAT_ID = YOUR_CHAT_ID

# ── Telegram API helpers ───────────────────────────────────────

def tg_send_message(chat_id, text):
    """Отправить сообщение в Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }).encode()
    
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        logger.error(f"sendMessage failed: {e}")
        return None


def tg_get_updates(offset=None, timeout=30):
    """Получить обновления от Telegram Bot API."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"timeout": timeout, "allowed_updates": ["message"]}
    if offset:
        params["offset"] = offset + 1
    
    data = json.dumps(params).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    
    try:
        with urllib.request.urlopen(req, timeout=timeout + 5) as resp:
            result = json.loads(resp.read())
            return result.get("result", [])
    except Exception as e:
        logger.error(f"getUpdates failed: {e}")
        return []


# ── Main loop ──────────────────────────────────────────────────

def main():
    logger.info("Starting Agent Smith with Telegram Bot...")
    
    app = AgentSmithApp(
        telegram_token=TELEGRAM_TOKEN,
        telegram_chat_id=CHAT_ID,
    )
    
    # Статус при запуске
    status = app.get_status()
    logger.info(f"Agent ready. Skills: {status['skills_loaded']}, IKKF: {status['ikkf']}")
    
    # Отправить приветственное сообщение
    tg_send_message(CHAT_ID, "🤖 *Agent Smith активирован*\n\nЯ готов к работе.\n\n...I know kung-fu 🥋")
    
    # Polling loop
    offset = None
    logger.info("Listening for messages...")
    
    while True:
        try:
            updates = tg_get_updates(offset=offset, timeout=30)
            
            for update in updates:
                offset = update["update_id"]
                
                message = update.get("message")
                if not message:
                    continue
                
                text = message.get("text")
                if not text:
                    continue
                
                chat_id = message["chat"]["id"]
                user = message.get("from", {}).get("username", "unknown")
                
                logger.info(f"Message from @{user}: {text[:80]}")
                
                # Обрабатываем через Agent Smith
                result = app.process_message(text)
                response = result.get("response", "")
                
                # Форматируем ответ
                if response:
                    formatted = f"🤖 *Agent Smith*\n\n{response}"
                    tg_send_message(chat_id, formatted)
                    logger.info(f"Response sent ({len(formatted)} chars)")
            
        except KeyboardInterrupt:
            logger.info("Stopped by user")
            break
        except Exception as e:
            logger.error(f"Loop error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
