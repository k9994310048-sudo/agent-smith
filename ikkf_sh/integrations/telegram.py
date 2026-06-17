"""
IKKF_SH — Telegram Bridge
Отправка сообщений в Telegram бот Agent Smith.

Использует Bot API напряжую (urllib, без внешних зависимостей).
"""

import json
import logging
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)


class TelegramBridge:
    """
    Мост между IKKF_SH и Telegram Bot API.
    
    Отправляет сообщения в чат пользователя.
    Поддерживает markdown-разметку.
    """

    BASE_URL = "https://api.telegram.org/bot{token}"

    def __init__(self, token: str, chat_id: int):
        self.token = token
        self.chat_id = chat_id
        self.base_url = self.BASE_URL.format(token=token)
        self._last_check = None
        self._last_error = None

    def send(self, text: str, parse_mode: str = "Markdown",
             disable_notification: bool = False) -> dict:
        """
        Отправка сообщения в Telegram.
        
        Args:
            text: Текст сообщения
            parse_mode: Markdown или HTML
            disable_notification: Без звука
            
        Returns:
            Ответ API
        """
        url = f"{self.base_url}/sendMessage"
        data = {
            "chat_id": self.chat_id,
            "text": text[:4096],  # лимит Telegram
            "parse_mode": parse_mode,
            "disable_notification": disable_notification,
        }

        try:
            body = json.dumps(data).encode()
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                if result.get("ok"):
                    logger.info(f"Msg sent: {text[:50]}...")
                    return {"status": "ok", "message_id": result["result"]["message_id"]}
                else:
                    self._last_error = result
                    return {"status": "error", "error": str(result)}
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"TG send failed: {e}")
            return {"status": "error", "error": str(e)}

    def check(self) -> dict:
        """Проверка работоспособности бота."""
        try:
            url = f"{self.base_url}/getMe"
            with urllib.request.urlopen(url, timeout=5) as resp:
                result = json.loads(resp.read())
                if result.get("ok"):
                    bot_info = result["result"]
                    self._last_check = {
                        "ok": True,
                        "bot_name": bot_info.get("first_name"),
                        "bot_username": bot_info.get("username"),
                    }
                    return self._last_check
        except Exception as e:
            self._last_check = {"ok": False, "error": str(e)}
            return self._last_check

    def get_updates(self, timeout: int = 30, limit: int = 10,
                    allowed_updates: list = None) -> list:
        """
        Получение обновлений (лонг-поллинг).
        Используется для получения команд от пользователя.
        """
        url = f"{self.base_url}/getUpdates"
        params = {"timeout": timeout, "limit": limit}
        if allowed_updates:
            params["allowed_updates"] = json.dumps(allowed_updates)

        import urllib.parse
        query = urllib.parse.urlencode(params)
        full_url = f"{url}?{query}"

        try:
            with urllib.request.urlopen(full_url, timeout=timeout + 5) as resp:
                result = json.loads(resp.read())
                if result.get("ok"):
                    return result.get("result", [])
                return []
        except Exception as e:
            logger.error(f"TG getUpdates failed: {e}")
            return []
