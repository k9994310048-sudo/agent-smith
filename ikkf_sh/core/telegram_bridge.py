"""
IKKF_SH — Show Me
Telegram Bridge: отправка сообщений в Telegram бот Agent Smith
"""

import json
import logging
import urllib.request
import urllib.parse
import os

logger = logging.getLogger(__name__)

SECRETS_PATH = "/root/.ikkf_secrets"
BOT_TOKEN = None


def _load_token() -> str:
    global BOT_TOKEN
    if BOT_TOKEN:
        return BOT_TOKEN
    with open(SECRETS_PATH) as f:
        for line in f:
            if "TELEGRAM_BOT_TOKEN=" in line:
                BOT_TOKEN = line.strip().split("=", 1)[1]
                return BOT_TOKEN
    raise ValueError("Bot token not found in secrets")


def send_telegram(chat_id: str, message: str) -> bool:
    """Отправить сообщение в Telegram"""
    try:
        token = _load_token()
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": message[:4096],
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
        if result.get("ok"):
            logger.info(f"Telegram sent to {chat_id}: {message[:60]}")
            return True
        logger.error(f"Telegram API error: {result}")
        return False
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False


def get_bot_info() -> dict:
    """Получить информацию о боте"""
    try:
        token = _load_token()
        url = f"https://api.telegram.org/bot{token}/getMe"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}
