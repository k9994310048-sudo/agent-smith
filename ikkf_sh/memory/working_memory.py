"""
IKKF_SH — Working Memory
Краткосрочный контекст для текущей задачи.

Принципы:
1. Хранит контекст текущей сессии (последние N сообщений)
2. Быстрый доступ (RAM, не SQLite)
3. Автоматическая очистка при завершении задачи
4. Сериализация в IKKF для долгосрочного хранения
"""

from __future__ import annotations
import time
import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from collections import deque

logger = logging.getLogger(__name__)

MAX_WORKING_MEMORY = 50  # Максимум записей в рабочей памяти


@dataclass
class MemoryEntry:
    """Запись в рабочей памяти."""
    role: str          # user | assistant | system | tool | observation
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict = field(default_factory=dict)
    importance: float = 0.5  # 0.0–1.0, для приоритизации при переполнении

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content[:500],  # Ограничиваем для компактности
            "timestamp": self.timestamp,
            "importance": self.importance,
        }


class WorkingMemory:
    """
    Краткосрочная память для текущей задачи.
    Реализована как deque с лимитом.
    """

    def __init__(self, max_size: int = MAX_WORKING_MEMORY):
        self.max_size = max_size
        self.entries: deque[MemoryEntry] = deque(maxlen=max_size)
        self.task_context: str = ""
        self.start_time: float = time.time()

    def add(self, role: str, content: str, importance: float = 0.5, metadata: Dict = None):
        entry = MemoryEntry(
            role=role,
            content=content,
            importance=importance,
            metadata=metadata or {},
        )
        self.entries.append(entry)

    def get_context(self, last_n: int = 20) -> str:
        """Возвращает контекст последних N записей."""
        recent = list(self.entries)[-last_n:]
        lines = []
        if self.task_context:
            lines.append(f"## Task: {self.task_context}\n")
        for entry in recent:
            role_label = entry.role.upper()
            lines.append(f"[{role_label}] {entry.content[:300]}")
            lines.append("")
        return "\n".join(lines)

    def get_summary(self) -> str:
        """Краткая сводка рабочей памяти."""
        duration = time.time() - self.start_time
        user_msgs = sum(1 for e in self.entries if e.role == "user")
        assistant_msgs = sum(1 for e in self.entries if e.role == "assistant")

        return (
            f"Working Memory Summary:\n"
            f"  Task: {self.task_context or 'N/A'}\n"
            f"  Duration: {duration:.0f}s\n"
            f"  Entries: {len(self.entries)}/{self.max_size}\n"
            f"  Messages: {user_msgs} user, {assistant_msgs} assistant\n"
        )

    def clear(self):
        """Очистка рабочей памяти."""
        self.entries.clear()
        self.task_context = ""
        self.start_time = time.time()

    def to_ikkf_facts(self) -> List[dict]:
        """Извлекает факты для сохранения в IKKF."""
        facts = []
        for entry in self.entries:
            if entry.importance >= 0.7 and entry.role == "assistant":
                facts.append({
                    "content": entry.content[:200],
                    "node_type": "fact",
                    "importance": entry.importance,
                    "source": "working_memory",
                })
        return facts

    def save_to_file(self, path: str):
        """Сохраняет рабочую память в JSON."""
        data = {
            "task": self.task_context,
            "start_time": self.start_time,
            "entries": [e.to_dict() for e in self.entries],
        }
        with open(path, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load_from_file(cls, path: str) -> "WorkingMemory":
        """Загружает рабочую память из JSON."""
        wm = cls()
        try:
            with open(path) as f:
                data = json.load(f)
            wm.task_context = data.get("task", "")
            wm.start_time = data.get("start_time", time.time())
            for e in data.get("entries", []):
                wm.add(
                    role=e["role"],
                    content=e["content"],
                    importance=e.get("importance", 0.5),
                )
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return wm
