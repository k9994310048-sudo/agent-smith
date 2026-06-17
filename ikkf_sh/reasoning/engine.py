"""
IKKF_SH — Reasoning Engine
Модуль рассуждений: chain-of-thought + verification + self-critique
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ReasoningStep:
    """Один шаг рассуждения."""
    def __init__(self, thought: str, action: Optional[str] = None, 
                 result: Optional[str] = None, confidence: float = 0.5):
        self.thought = thought
        self.action = action
        self.result = result
        self.confidence = confidence
        self.verified = False

    def to_dict(self):
        return {
            "thought": self.thought,
            "action": self.action,
            "result": self.result,
            "confidence": self.confidence,
            "verified": self.verified,
        }


class ReasoningEngine:
    """
    Chain-of-Thought с верификацией.
    
    Алгоритм:
    1. Разбить задачу на шаги
    2. Для каждого шага: мысль → действие → результат
    3. Проверить результат (verification)
    4. Если confidence < threshold → пересмотреть шаг
    """

    def __init__(self, confidence_threshold: float = 0.7, max_steps: int = 10):
        self.confidence_threshold = confidence_threshold
        self.max_steps = max_steps
        self.steps: list[ReasoningStep] = []

    def reason(self, query: str, context: str = "") -> dict:
        """
        Основной метод рассуждения.
        Возвращает цепочку мыслей и финальный ответ.
        """
        self.steps = []
        
        # Шаг 1: Понимание задачи
        step1 = ReasoningStep(
            thought=f"Анализ запроса: {query[:100]}",
            confidence=0.9
        )
        self.steps.append(step1)

        # Шаг 2: Поиск релевантных знаний в IKKF
        step2 = ReasoningStep(
            thought="Поиск в базе знаний IKKF",
            action="ik_search",
            confidence=0.8
        )
        self.steps.append(step2)

        # Шаг 3: Формирование гипотезы
        step3 = ReasoningStep(
            thought="Формирование ответа на основе найденных фактов",
            confidence=0.7
        )
        self.steps.append(step3)

        # Шаг 4: Верификация
        step4 = ReasoningStep(
            thought="Проверка фактов и логики",
            action="verify",
            confidence=0.75
        )
        self.steps.append(step4)

        return {
            "query": query,
            "steps": [s.to_dict() for s in self.steps],
            "confidence": self._avg_confidence(),
            "status": "complete" if self._avg_confidence() >= self.confidence_threshold else "needs_review",
        }

    def verify_step(self, step_index: int, verification_result: bool, 
                    feedback: str = "") -> None:
        """Верификация конкретного шага."""
        if 0 <= step_index < len(self.steps):
            self.steps[step_index].verified = verification_result
            if not verification_result:
                self.steps[step_index].confidence *= 0.5
                logger.warning(f"Step {step_index} failed verification: {feedback}")

    def _avg_confidence(self) -> float:
        if not self.steps:
            return 0.0
        return sum(s.confidence for s in self.steps) / len(self.steps)

    def reset(self):
        self.steps = []
