"""
IKKF_SH — Show Me
Skill System: создание, хранение, эволюция навыков
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SKILLS_DIR = os.path.expanduser("~/projects/ikkf_sh/skills")


class Skill:
    """
    Навык — это переиспользуемый модуль поведения.
    Хранится как SKILL.md + метаданные.
    """

    def __init__(self, name: str, description: str,
                 content: str, version: str = "1.0.0",
                 tags: List[str] = None,
                 performance_score: float = 0.0,
                 usage_count: int = 0):
        self.name = name
        self.description = description
        self.content = content
        self.version = version
        self.tags = tags or []
        self.performance_score = performance_score
        self.usage_count = usage_count
        self.created_at = time.time()
        self.updated_at = time.time()

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "tags": self.tags,
            "performance_score": self.performance_score,
            "usage_count": self.usage_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def save(self):
        """Сохранить навык в файловую систему"""
        os.makedirs(SKILLS_DIR, exist_ok=True)
        skill_dir = os.path.join(SKILLS_DIR, self.name)
        os.makedirs(skill_dir, exist_ok=True)

        # Метаданные
        with open(os.path.join(skill_dir, "meta.json"), "w") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

        # Содержимое (SKILL.md)
        with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
            f.write(self.content)

        logger.info(f"Skill saved: {self.name} v{self.version}")

    @classmethod
    def load(cls, name: str) -> Optional["Skill"]:
        """Загрузить навык"""
        skill_dir = os.path.join(SKILLS_DIR, name)
        meta_path = os.path.join(skill_dir, "meta.json")
        content_path = os.path.join(skill_dir, "SKILL.md")

        if not os.path.exists(meta_path):
            return None

        with open(meta_path) as f:
            meta = json.load(f)

        content = ""
        if os.path.exists(content_path):
            with open(content_path) as f:
                content = f.read()

        skill = cls(
            name=meta["name"],
            description=meta["description"],
            content=content,
            version=meta.get("version", "1.0.0"),
            tags=meta.get("tags", []),
            performance_score=meta.get("performance_score", 0.0),
            usage_count=meta.get("usage_count", 0),
        )
        skill.created_at = meta.get("created_at", time.time())
        skill.updated_at = meta.get("updated_at", time.time())
        return skill

    @classmethod
    def list_skills(cls) -> List[Dict]:
        """Список всех навыков"""
        if not os.path.exists(SKILLS_DIR):
            return []
        skills = []
        for name in os.listdir(SKILLS_DIR):
            skill = cls.load(name)
            if skill:
                skills.append(skill.to_dict())
        return skills


class SkillEvolver:
    """
    Эволюция навыков:
    - Отслеживает успешность использования
    - Предлагает улучшения
    - Версионирование
    """

    def __init__(self):
        self.feedback_log: List[Dict] = []

    def record_usage(self, skill_name: str, success: bool,
                     feedback: str = ""):
        """Записать результат использования навыка"""
        self.feedback_log.append({
            "skill": skill_name,
            "success": success,
            "feedback": feedback,
            "timestamp": time.time()
        })

        # Обновляем performance_score
        skill = Skill.load(skill_name)
        if skill:
            skill.usage_count += 1
            # Простой rolling average
            if success:
                skill.performance_score = min(1.0,
                    skill.performance_score + 0.05)
            else:
                skill.performance_score = max(0.0,
                    skill.performance_score - 0.1)
            skill.updated_at = time.time()
            skill.save()

    def get_skill_score(self, skill_name: str) -> float:
        """Получить текущую оценку навыка"""
        skill = Skill.load(skill_name)
        if not skill:
            return 0.0
        return skill.performance_score

    def suggest_improvements(self, skill_name: str) -> List[str]:
        """Предложить улучшения на основе обратной связи"""
        feedbacks = [
            f for f in self.feedback_log
            if f["skill"] == skill_name and not f["success"]
        ]
        suggestions = []
        for fb in feedbacks[-5:]:  # Последние 5 неудач
            suggestions.append(f"Failed: {fb['feedback']}")
        return suggestions
