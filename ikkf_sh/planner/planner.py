"""
IKKF_SH — Action Planner
Декомпозиция задач, выбор инструментов, планирование действий.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ActionStep:
    """Один шаг плана действий."""
    def __init__(self, description: str, tool: str = None, 
                 params: dict = None, depends_on: int = None):
        self.description = description
        self.tool = tool
        self.params = params or {}
        self.depends_on = depends_on  # индекс предыдущего шага
        self.status = "pending"  # pending | in_progress | done | failed
        self.result = None

    def to_dict(self):
        return {
            "description": self.description,
            "tool": self.tool,
            "params": self.params,
            "depends_on": self.depends_on,
            "status": self.status,
            "result": self.result,
        }


class ActionPlanner:
    """
    Планировщик действий.
    
    Принимает задачу → декомпозирует на шаги → определяет инструменты → выполняет.
    """

    # Доступные инструменты (расширяемый список)
    AVAILABLE_TOOLS = {
        "ik_search": "Поиск в базе знаний IKKF",
        "ik_store": "Сохранение факта в IKKF",
        "ik_context": "Получение RAG-контекста",
        "ik_stats": "Статистика графа",
        "web_search": "Поиск в интернете",
        "web_extract": "Извлечение контента с URL",
        "terminal": "Выполнение shell-команды",
        "browser": "Управление браузером",
        "file_read": "Чтение файла",
        "file_write": "Запись файла",
        "telegram_send": "Отправка сообщения в Telegram",
        "skill_load": "Загрузка навыка из IKKF_SH",
        "agent_spawn": "Создание дочернего агента",
        "agent_wait": "Ожидание завершения дочернего агента",
    }

    def plan(self, task: str, context: dict = None) -> dict:
        """
        Декомпозиция задачи на шаги.
        Возвращает план действий.
        """
        steps = []
        
        # Анализ задачи → определение необходимых инструментов
        task_lower = task.lower()

        # Шаг 1: Всегда начинаем с поиска в памяти
        steps.append(ActionStep(
            description="Поиск релевантных знаний в IKKF",
            tool="ik_search",
            params={"query": task, "limit": 5}
        ))

        # Шаг 2: Если нужен веб-поиск
        if any(kw in task_lower for kw in ["найти", "новости", "интернет", "поиск", "узнать"]):
            steps.append(ActionStep(
                description="Поиск в интернете",
                tool="web_search",
                params={"query": task, "limit": 10},
                depends_on=0
            ))

        # Шаг 3: Сохранение результата
        steps.append(ActionStep(
            description="Сохранение результата в IKKF",
            tool="ik_store",
            params={"importance": 0.7},
            depends_on=len(steps) - 1
        ))

        return {
            "task": task,
            "steps": [s.to_dict() for s in steps],
            "total_steps": len(steps),
        }

    def execute_step(self, step: ActionStep) -> bool:
        """Выполнение одного шага."""
        step.status = "in_progress"
        logger.info(f"Executing: {step.description} (tool: {step.tool})")
        
        try:
            # Здесь будет вызов соответствующего инструмента
            step.status = "done"
            step.result = f"Completed: {step.description}"
            return True
        except Exception as e:
            step.status = "failed"
            step.result = str(e)
            logger.error(f"Step failed: {step.description}: {e}")
            return False

    def get_available_tools(self) -> dict:
        """Список доступных инструментов."""
        return self.AVAILABLE_TOOLS.copy()
