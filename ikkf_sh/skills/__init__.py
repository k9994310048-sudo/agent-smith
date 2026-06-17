"""
IKKF_SH — Skill System
Создание, хранение, эволюция навыков.

Навык — это структурированная инструкция для выполнения конкретной задачи.
Каждый навык хранится как SKILL.md и может эволюционировать.
"""

import os
import json
import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SKILLS_DIR = os.path.join(os.path.dirname(__file__), "..", "skills")


class Skill:
    """Один навык."""

    def __init__(self, name: str, content: str, version: str = "1.0.0",
                 tags: list = None, performance: float = 0.0):
        self.name = name
        self.content = content
        self.version = version
        self.tags = tags or []
        self.performance = performance  # 0.0 - 1.0
        self.usage_count = 0
        self.created = datetime.utcnow().isoformat()
        self.updated = self.created
        self.hash = hashlib.md5(content.encode()).hexdigest()[:8]

    def to_dict(self):
        return {
            "name": self.name,
            "version": self.version,
            "tags": self.tags,
            "performance": self.performance,
            "usage_count": self.usage_count,
            "created": self.created,
            "updated": self.updated,
            "hash": self.hash,
        }

    def increment_usage(self):
        self.usage_count += 1
        self.updated = datetime.utcnow().isoformat()

    def update_performance(self, score: float):
        """Обновление оценки эффективности (EMA)."""
        alpha = 0.3
        self.performance = alpha * score + (1 - alpha) * self.performance


class SkillSystem:
    """
    Система управления навыками.
    
    Функции:
    - Создание навыка
    - Загрузка навыка по имени
    - Поиск навыков по тегам
    - Эволюция: performance tracking, versioning
    - Сохранение/загрузка из файлов
    """

    def __init__(self, skills_dir: str = None):
        self.skills_dir = skills_dir or SKILLS_DIR
        self.skills: dict[str, Skill] = {}
        os.makedirs(self.skills_dir, exist_ok=True)

    def create_skill(self, name: str, content: str, 
                     tags: list = None) -> Skill:
        """Создание нового навыка."""
        skill = Skill(name=name, content=content, tags=tags or [])
        self.skills[name] = skill
        self._save_skill(skill)
        logger.info(f"Skill created: {name}")
        return skill

    def load_skill(self, name: str) -> Optional[Skill]:
        """Загрузка навыка из файла."""
        path = os.path.join(self.skills_dir, f"{name}.md")
        if os.path.exists(path):
            with open(path, "r") as f:
                content = f.read()
            skill = Skill(name=name, content=content)
            self.skills[name] = skill
            return skill
        return None

    def find_skills(self, tag: str = None, min_performance: float = 0.0) -> list:
        """Поиск навыков по фильтрам."""
        results = []
        for skill in self.skills.values():
            if tag and tag not in skill.tags:
                continue
            if skill.performance < min_performance:
                continue
            results.append(skill)
        return sorted(results, key=lambda s: s.performance, reverse=True)

    def evolve_skill(self, name: str, feedback: str, score: float):
        """
        Эволюция навыка на основе обратной связи.
        - Обновляет performance
        - Увеличивает версию при значительных изменениях
        """
        if name not in self.skills:
            logger.warning(f"Skill not found: {name}")
            return

        skill = self.skills[name]
        skill.update_performance(score)
        skill.increment_usage()

        # Bumped version при значительном изменении
        old_perf = skill.performance
        if abs(score - old_perf) > 0.3:
            parts = skill.version.split(".")
            parts[-1] = str(int(parts[-1]) + 1)
            skill.version = ".".join(parts)

        self._save_skill(skill)
        logger.info(f"Skill evolved: {name} (perf: {skill.performance:.2f}, v{skill.version})")

    def _save_skill(self, skill: Skill):
        """Сохранение навыка в файл."""
        path = os.path.join(self.skills_dir, f"{skill.name}.md")
        header = f"""---
name: {skill.name}
version: {skill.version}
tags: {', '.join(skill.tags)}
performance: {skill.performance:.2f}
usage: {skill.usage_count}
updated: {skill.updated}
hash: {skill.hash}
---

"""
        with open(path, "w") as f:
            f.write(header + skill.content)


# Предустановленные навыки
DEFAULT_SKILLS = {
    "deep_search": {
        "tags": ["search", "research"],
        "content": """# Deep Search

## Описание
Глубокий поиск информации в интернете с анализом источников.

## Алгоритм
1. Разбить запрос на ключевые слова
2. Выполнить web_search с limit=20
3. Извлечь контент с топ-5 URL (web_extract)
4. Проанализировать и структурировать результаты
5. Сохранить ключевые факты в IKKF
6. Вернуть сводку с источниками

## Параметры
- query: поисковый запрос
- depth: глубина поиска (shallow|medium|deep)
- max_sources: максимум источников для анализа
""",
    },
    "fact_check": {
        "tags": ["verification", "quality"],
        "content": """# Fact Check

## Описание
Проверка фактов и утверждений на достоверность.

## Алгоритм
1. Извлечь утверждения из текста
2. Для каждого утверждения:
   a. Поиск в IKKF
   b. Поиск в интернете (если нет в IKKF)
   c. Сравнение источников
   d. Присвоение confidence score
3. Вернуть отчёт с оценками

## Критерии оценки
- 0.9+: Подтверждено несколькими источниками
- 0.7-0.9: Подтверждено одним источником
- 0.5-0.7: Частично подтверждено
- <0.5: Не подтверждено / опровергнуто
""",
    },
    "document_analysis": {
        "tags": ["analysis", "documents"],
        "content": """# Document Analysis

## Описание
Анализ документов (PDF, DOCX, TXT) и извлечение ключевой информации.

## Алгоритм
1. Определить тип документа
2. Извлечь текст (pymupdf / marker-pdf)
3. Выделить ключевые сущности, факты, связи
4. Сохранить в IKKF как узлы графа
5. Вернуть summary + key facts
""",
    },
}
