"""
Планировщик задач для Agent Smith.
Позволяет разбивать сложные запросы на последовательность простых шагов.
"""
import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class ActionStep:
    def __init__(self, step_id: int, description: str, tool: str = None, params: dict = None):
        self.step_id = step_id
        self.description = description
        self.tool = tool
        self.params = params or {}

class TaskPlanner:
    def __init__(self, llm):
        self.llm = llm

    def plan(self, task: str, tools_info: str) -> List[ActionStep]:
        """Разбить задачу на шаги."""
        prompt = f"""Ты — планировщик задач для Agent Smith.
Твоя цель: разбить сложную задачу пользователя на 2-4 конкретных шага.

Задача: {task}

Доступные инструменты:
{tools_info}

Ответь ТОЛЬКО в формате JSON:
[
  {{"id": 1, "description": "что сделать", "tool": "имя_инструмента", "params": {{"аргумент": "значение"}}}},
  {{"id": 2, "description": "что сделать дальше", "tool": "имя_инструмента", "params": {{"аргумент": "значение"}}}}
]

Если задача простая и не требует инструментов, верни пустой список [].
"""
        try:
            # Для планирования используем небольшое количество токенов
            res = self.llm.generate([{"role": "user", "content": prompt}], max_tokens=512)
            content = res.get("content", "").strip()

            # Пытаемся найти JSON в ответе
            import re
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                plan_data = json.loads(json_match.group())
                steps = []
                for item in plan_data:
                    steps.append(ActionStep(
                        step_id=item.get("id"),
                        description=item.get("description"),
                        tool=item.get("tool"),
                        params=item.get("params", {})
                    ))
                return steps
        except Exception as e:
            logger.error(f"Planning failed: {e}")

        return []
