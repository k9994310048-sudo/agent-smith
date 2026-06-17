"""
Модуль саморефлексии для Agent Smith.
Позволяет агенту проверять свои ответы на фактические ошибки и логику.
"""
import logging

logger = logging.getLogger(__name__)

class SelfReflection:
    def __init__(self, llm):
        self.llm = llm

    def reflect(self, question: str, answer: str) -> str:
        """Проверить ответ и при необходимости улучшить его."""
        prompt = f"""Ты — критик для Agent Smith. Проверь ответ на вопрос на наличие фактических ошибок или логических противоречий.

Вопрос: {question}
Ответ: {answer}

Если ответ верный и точный, напиши "OK".
Если в ответе есть ошибки, напиши исправленную версию ответа.
Будь краток.
"""
        try:
            res = self.llm.generate([{"role": "user", "content": prompt}], max_tokens=512)
            content = res.get("content", "").strip()

            if content.upper() == "OK" or "ОК" in content.upper():
                return answer
            return content
        except Exception as e:
            logger.error(f"Reflection failed: {e}")
            return answer
