"""
IKKF_SH — IKKF Bridge
Мост между IKKF (память) и IKKF_SH (навыки/действия).
"""

import json
import logging
import urllib.request
import urllib.parse
from typing import Optional

logger = logging.getLogger(__name__)

IKKF_API_URL = "http://127.0.0.1:8766"


class IKKFBridge:
    """
    Интеграция с IKKF Graph API.
    
    Обеспечивает:
    - Поиск фактов
    - Сохранение новых фактов
    - Получение RAG-контекста
    - Проверку здоровья
    """

    def __init__(self, api_url: str = IKKF_API_URL):
        self.api_url = api_url

    def _request(self, method: str, path: str, data: dict = None, 
                 timeout: int = 10) -> dict:
        """HTTP-запрос к IKKF API."""
        url = f"{self.api_url}{path}"
        if method == "GET" and data:
            url += "?" + urllib.parse.urlencode(data)

        body = None
        headers = {}
        if method == "POST" and data:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())

    def health(self) -> dict:
        """Проверка здоровья IKKF."""
        try:
            return self._request("GET", "/health", timeout=3)
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def search(self, query: str, limit: int = 5) -> list:
        """Поиск фактов в IKKF."""
        try:
            result = self._request("GET", "/search/hybrid", 
                                   {"q": query, "limit": limit})
            return result.get("results", [])
        except Exception as e:
            logger.error(f"IKKF search failed: {e}")
            return []

    def store(self, content: str, importance: float = 0.7,
              tags: list = None) -> dict:
        """Сохранение факта в IKKF."""
        try:
            result = self._request("POST", "/node", {
                "content": content,
                "node_type": "fact",
                "importance": importance,
                "tags": tags or [],
                "source": "ikkf_sh",
            })
            return result
        except Exception as e:
            logger.error(f"IKKF store failed: {e}")
            return {}

    def rag(self, query: str, limit: int = 5) -> dict:
        """Получение RAG-контекста."""
        try:
            return self._request("POST", "/rag", {
                "query": query,
                "limit": limit,
            })
        except Exception as e:
            logger.error(f"IKKF RAG failed: {e}")
            return {}

    def stats(self) -> dict:
        """Статистика графа."""
        try:
            return self._request("GET", "/stats")
        except Exception as e:
            logger.error(f"IKKF stats failed: {e}")
            return {}
