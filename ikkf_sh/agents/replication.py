"""
Agent Smith — Self-Replication Engine
Контролируемое самокопирование для параллельного выполнения задач.

Принципы:
- Лимит на количество клонов (max_clones)
- Каждый клон имеет свой ID и parent_id
- Клоны отчитываются перед родителем
- Родитель собирает результаты
- При завершении — клоны уничтожаются (или идут в сон)
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

MAX_CLONES_DEFAULT = 5  # Максимум клонов одновременно


class ReplicationEngine:
    """
    Движок самокопирования.
    
    Управляет жизненным циклом клонов:
    - Создание
    - Распределение задач
    - Сбор результатов
    - Уничтожение / гибернация
    """

    def __init__(self, max_clones: int = MAX_CLONES_DEFAULT):
        self.max_clones = max_clones
        self.clones: dict[str, dict] = {}
        self.active_count = 0

    def can_replicate(self) -> bool:
        """Проверка возможности клонирования."""
        return self.active_count < self.max_clones

    def create_clone(self, task: str, parent_id: str,
                     resources: dict = None) -> Optional[dict]:
        """
        Создание клона для выполнения задачи.
        
        Args:
            task: Задача для клона
            parent_id: ID родительского агента
            resources: Ресурсы для клона (memory_limit, cpu_limit)
            
        Returns:
            Данные клона или None (если лимит превышен)
        """
        if not self.can_replicate():
            logger.warning(f"Clone limit reached ({self.max_clones})")
            return None

        clone_id = str(uuid.uuid4())[:8]
        clone = {
            "id": clone_id,
            "parent_id": parent_id,
            "task": task,
            "state": "created",
            "created": datetime.utcnow().isoformat(),
            "resources": resources or {"memory_mb": 256, "cpu_percent": 25},
            "result": None,
            "feedback": None,
        }

        self.clones[clone_id] = clone
        self.active_count += 1

        logger.info(f"Clone created: {clone_id} for task: {task[:60]}")
        return clone

    def destroy_clone(self, clone_id: str):
        """Уничтожение клона."""
        if clone_id in self.clones:
            del self.clones[clone_id]
            self.active_count -= 1
            logger.info(f"Clone destroyed: {clone_id}")

    def hibernate_clone(self, clone_id: str):
        """Гибернация клон (сохранение состояния, освобождение ресурсов)."""
        if clone_id in self.clones:
            self.clones[clone_id]["state"] = "hibernating"
            logger.info(f"Clone hibernated: {clone_id}")

    def get_clone_status(self, clone_id: str) -> Optional[dict]:
        """Статус клона."""
        return self.clones.get(clone_id)

    def get_all_statuses(self) -> list:
        """Статусы всех клонов."""
        return list(self.clones.values())

    def collect_results(self, parent_id: str) -> list:
        """Сбор результатов от всех клонов родителя."""
        results = []
        for clone in self.clones.values():
            if clone["parent_id"] == parent_id and clone["result"]:
                results.append(clone)
        return results

    def get_stats(self) -> dict:
        """Статистика репликации."""
        return {
            "max_clones": self.max_clones,
            "active": self.active_count,
            "available": self.max_clones - self.active_count,
            "total_created": len(self.clones),
            "by_state": self._count_by_state(),
        }

    def _count_by_state(self) -> dict:
        counts = {}
        for clone in self.clones.values():
            state = clone["state"]
            counts[state] = counts.get(state, 0) + 1
        return counts
