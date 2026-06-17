"""
IKKF_SH — Show Me
Working Memory: краткосрочный контекст для текущей задачи
"""

import json
import logging
import time
from collections import deque
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class WorkingMemory:
    """
    Краткосрочная память для текущей задачи.
    Отличается от IKKF (L2) — здесь только текущий контекст.
    Очищается при завершении задачи.
    """

    def __init__(self, max_items: int = 50):
        self.max_items = max_items
        self.items: deque = deque(maxlen=max_items)
        self.variables: Dict[str, Any] = {}

    def add(self, role: str, content: str, metadata: dict = None):
        item = {
            "role": role,
            "content": content,
            "timestamp": time.time(),
            "metadata": metadata or {}
        }
        self.items.append(item)
        logger.debug(f"WM add [{role}]: {content[:60]}")

    def get_context(self, last_n: int = 20) -> List[dict]:
        """Получить последние N элементов"""
        return list(self.items)[-last_n:]

    def set_var(self, key: str, value: Any):
        self.variables[key] = value

    def get_var(self, key: str, default: Any = None) -> Any:
        return self.variables.get(key, default)

    def clear(self):
        self.items.clear()
        self.variables.clear()

    def summary(self) -> str:
        """Краткая сводка по рабочей памяти"""
        lines = [f"Working Memory: {len(self.items)} items"]
        for item in list(self.items)[-5:]:
            role = item["role"]
            content = item["content"][:80]
            lines.append(f"  [{role}] {content}")
        return "\n".join(lines)
