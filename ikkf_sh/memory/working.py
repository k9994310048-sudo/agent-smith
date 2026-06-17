"""
IKKF_SH — Working Memory
Краткосрочный контекст для текущей задачи.
"""

import json
import logging
from collections import deque
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class WorkingMemory:
    """
    Рабочая память агента.
    
    Хранит контекст текущей задачи:
    - История действий и результатов
    - Промежуточные данные
    - Текущее состояние
    
    Ограничена по размеру (FIFO) для экономии RAM.
    """

    def __init__(self, max_items: int = 100):
        self.max_items = max_items
        self.items: deque = deque(maxlen=max_items)
        self.metadata: dict = {}
        self.created = datetime.utcnow().isoformat()

    def add(self, key: str, value: any, metadata: dict = None):
        """Добавление элемента в рабочую память."""
        item = {
            "key": key,
            "value": value,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.items.append(item)

    def get(self, key: str) -> Optional[any]:
        """Получение значения по ключу (последнее)."""
        for item in reversed(self.items):
            if item["key"] == key:
                return item["value"]
        return None

    def get_all(self, key: str) -> list:
        """Получение всех значений по ключу."""
        return [item["value"] for item in self.items if item["key"] == key]

    def set_metadata(self, key: str, value: any):
        """Установка метаданных."""
        self.metadata[key] = value

    def get_metadata(self, key: str) -> Optional[any]:
        return self.metadata.get(key)

    def clear(self):
        """Очистка рабочей памяти."""
        self.items.clear()
        self.metadata.clear()

    def to_dict(self) -> dict:
        return {
            "items": list(self.items),
            "metadata": self.metadata,
            "created": self.created,
            "size": len(self.items),
        }

    def summary(self) -> str:
        """Краткая сводка."""
        keys = set(item["key"] for item in self.items)
        return f"WorkingMemory: {len(self.items)} items, keys: {', '.join(keys)}"
