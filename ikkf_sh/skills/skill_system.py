"""
IKKF_SH — Skill System
Создание, хранение, эволюция навыков (skills).

Каждый навык — это SKILL.md + метаданные.
Навыки хранятся в папке skills/ и регистрируются в IKKF графе.
"""

from __future__ import annotations
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SKILLS_DIR = os.path.join(os.path.dirname(__file__), "..", "skills")


@dataclass
class Skill:
    """Один навык."""
    name: str
    description: str
    content: str  # Полный текст SKILL.md
    version: str = "1.0"
    author: str = "agent"
    tags: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    success_count: int = 0
    fail_count: int = 0
    last_used: float = 0.0  # timestamp
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def path(self) -> str:
        return os.path.join(SKILLS_DIR, self.name, "SKILL.md")

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.fail_count
        if total == 0:
            return 0.5  # Нейтральная при отсутствии данных
        return self.success_count / total

    def record_success(self):
        self.success_count += 1
        self.last_used = time.time()
        self.updated_at = time.time()

    def record_failure(self):
        self.fail_count += 1
        self.last_used = time.time()
        self.updated_at = time.time()

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "tags": self.tags,
            "dependencies": self.dependencies,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "success_rate": round(self.success_rate, 3),
            "last_used": self.last_used,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class SkillSystem:
    """
    Система управления навыками.
    
    Функции:
    - Создание навыков из опыта (самообучение)
    - Хранение в файловой системе + индексация в IKKF
    - Performance tracking (success/fail rate)
    - Эволюция: обновление навыков на основе ошибок
    - Ранжирование: выбор лучшего навыка для задачи
    """

    def __init__(self, skills_dir: str = None):
        self.skills: dict[str, Skill] = {}
        self.skills_dir = skills_dir or SKILLS_DIR
        os.makedirs(self.skills_dir, exist_ok=True)

    def create_skill(
        self,
        name: str,
        description: str,
        content: str,
        tags: list[str] = None,
        dependencies: list[str] = None,
        author: str = "agent",
    ) -> Skill:
        """Создать новый навык."""
        skill = Skill(
            name=name,
            description=description,
            content=content,
            tags=tags or [],
            dependencies=dependencies or [],
            author=author,
        )

        # Сохранить в файловую систему
        skill_dir = os.path.join(self.skills_dir, name)
        os.makedirs(skill_dir, exist_ok=True)

        with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(content)

        # Метаданные
        with open(os.path.join(skill_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(skill.to_dict(), f, ensure_ascii=False, indent=2)

        self.skills[name] = skill
        logger.info(f"Skill created: {name}")
        return skill

    def load_skill(self, name: str) -> Optional[Skill]:
        """Загрузить навык с диска."""
        skill_dir = os.path.join(self.skills_dir, name)
        skill_file = os.path.join(skill_dir, "SKILL.md")
        meta_file = os.path.join(skill_dir, "meta.json")

        if not os.path.exists(skill_file):
            return None

        with open(skill_file, "r", encoding="utf-8") as f:
            content = f.read()

        metadata = {}
        if os.path.exists(meta_file):
            with open(meta_file, "r", encoding="utf-8") as f:
                metadata = json.load(f)

        skill = Skill(
            name=name,
            description=metadata.get("description", ""),
            content=content,
            version=metadata.get("version", "1.0"),
            author=metadata.get("author", "agent"),
            tags=metadata.get("tags", []),
            dependencies=metadata.get("dependencies", []),
            success_count=metadata.get("success_count", 0),
            fail_count=metadata.get("fail_count", 0),
        )

        self.skills[name] = skill
        return skill

    def load_all(self) -> list[Skill]:
        """Загрузить все навыки из директории."""
        if not os.path.exists(self.skills_dir):
            return []

        for name in os.listdir(self.skills_dir):
            skill_dir = os.path.join(self.skills_dir, name)
            if os.path.isdir(skill_dir) and os.path.exists(os.path.join(skill_dir, "SKILL.md")):
                self.load_skill(name)

        return list(self.skills.values())

    def find_best_skill(self, query: str) -> Optional[Skill]:
        """Найти лучший навык для задачи (простой поиск по тегам и описанию)."""
        query_words = set(query.lower().split())
        best_match = None
        best_score = 0

        for skill in self.skills.values():
            score = 0

            # Совпадение по тегам
            for tag in skill.tags:
                if tag.lower() in query.lower():
                    score += 3

            # Совпадение по описанию
            desc_words = set(skill.description.lower().split())
            score += len(query_words & desc_words)

            # Совпадение по имени
            if skill.name.lower() in query.lower():
                score += 5

            # Бонус за success rate
            score += skill.success_rate * 2

            if score > best_score:
                best_score = score
                best_match = skill

        return best_match

    def evolve_skill(self, name: str, fix: str, reason: str) -> Optional[Skill]:
        """
        Эволюция навыка: обновление на основе ошибки.
        Добавляет секцию Pitfalls или обновляет существующую.
        """
        skill = self.skills.get(name) or self.load_skill(name)
        if not skill:
            return None

        # Добавляем исправление в конец файла
        if "## Известные проблемы и решения" not in skill.content:
            skill.content += "\n\n## Известные проблемы и решения\n"

        timestamp = time.strftime("%Y-%m-%d")
        skill.content += f"\n### {timestamp}\n**Проблема:** {reason}\n**Решение:** {fix}\n"

        skill.version = f"{float(skill.version) + 0.1:.1f}"
        skill.updated_at = time.time()

        # Сохранить
        with open(skill.path, "w", encoding="utf-8") as f:
            f.write(skill.content)

        with open(os.path.join(os.path.dirname(skill.path), "meta.json"), "w", encoding="utf-8") as f:
            json.dump(skill.to_dict(), f, ensure_ascii=False, indent=2)

        logger.info(f"Skill evolved: {name} -> v{skill.version}")
        return skill
