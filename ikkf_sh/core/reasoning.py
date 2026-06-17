"""
IKKF_SH — Show Me
Reasoning Engine: chain-of-thought + verification
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ReasoningStep:
    """Один шаг рассуждения"""

    def __init__(self, thought: str, action: Optional[str] = None,
                 action_input: Optional[str] = None,
                 observation: Optional[str] = None,
                 confidence: float = 0.0):
        self.thought = thought
        self.action = action
        self.action_input = action_input
        self.observation = observation
        self.confidence = confidence

    def to_dict(self) -> dict:
        return {
            "thought": self.thought,
            "action": self.action,
            "action_input": self.action_input,
            "observation": self.observation,
            "confidence": self.confidence,
        }


class ReasoningEngine:
    """
    Chain-of-Thought + Self-Verification
    Каждый ответ проходит цикл:
    Think → Act → Observe → Verify → Conclude
    """

    def __init__(self, max_steps: int = 10):
        self.max_steps = max_steps
        self.steps: List[ReasoningStep] = []

    def reset(self):
        self.steps = []

    def think(self, thought: str) -> ReasoningStep:
        step = ReasoningStep(thought=thought)
        self.steps.append(step)
        logger.debug(f"[THINK] {thought[:80]}")
        return step

    def act(self, step: ReasoningStep, action: str, action_input: str):
        step.action = action
        step.action_input = action_input
        logger.debug(f"[ACT] {action}({action_input[:80]})")

    def observe(self, step: ReasoningStep, observation: str):
        step.observation = observation
        logger.debug(f"[OBSERVE] {observation[:80]}")

    def verify(self, step: ReasoningStep, confidence: float,
               verdict: str = "") -> bool:
        """Проверка шага. confidence 0.0-1.0"""
        step.confidence = confidence
        passed = confidence >= 0.6
        if not passed:
            logger.warning(f"[VERIFY FAIL] confidence={confidence:.2f} {verdict}")
        return passed

    def can_conclude(self) -> bool:
        """Можно ли завершить рассуждение"""
        if not self.steps:
            return False
        last = self.steps[-1]
        # Завершаем если последний шаг достаточно уверенный
        # и нет pending action
        return (last.confidence >= 0.8 and
                last.action is None and
                last.observation is not None)

    def get_trace(self) -> List[dict]:
        return [s.to_dict() for s in self.steps]


class VerificationLoop:
    """
    Проверка фактов и выводов.
    Сверяет с IKKF (знания), проверяет логику, оценивает confidence.
    """

    def __init__(self, ikkf_api_url: str = "http://127.0.0.1:8766"):
        self.api_url = ikkf_api_url

    def verify_fact(self, claim: str) -> Tuple[bool, float, str]:
        """
        Проверка факта через IKKF.
        Возвращает: (is_supported, confidence, evidence)
        """
        try:
            import urllib.request
            import urllib.parse
            params = urllib.parse.urlencode({
                "q": claim[:100],
                "search_type": "hybrid",
                "limit": 3
            })
            url = f"{self.api_url}/search/hybrid?{params}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read())
            results = result.get("results", [])
            if not results:
                return False, 0.0, "No supporting evidence in IKKF"
            best = results[0]
            score = best.get("vec_score", 0)
            content = best.get("content", "")[:100]
            if score > 0.5:
                return True, score, content
            return False, score, content
        except Exception as e:
            logger.warning(f"Verification failed: {e}")
            return False, 0.0, str(e)

    def verify_chain(self, steps: List[ReasoningStep]) -> Tuple[bool, float]:
        """
        Проверка всей цепочки рассуждений.
        Возвращает: (all_passed, min_confidence)
        """
        if not steps:
            return False, 0.0
        confidences = [s.confidence for s in steps if s.confidence > 0]
        if not confidences:
            return False, 0.0
        min_conf = min(confidences)
        all_passed = all(c >= 0.6 for c in confidences)
        return all_passed, min_conf
