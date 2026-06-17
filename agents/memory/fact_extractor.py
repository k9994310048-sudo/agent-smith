"""
Модуль извлечения фактов (Async v2.1).
"""
import json
import logging
import re
from typing import List, Dict

logger = logging.getLogger(__name__)

class FactExtractor:
    def __init__(self, llm):
        self.llm = llm

    async def extract(self, user_msg: str, assistant_msg: str) -> List[Dict]:
        """Извлечь факты асинхронно."""
        prompt = f"""Проанализируй диалог и извлеки ключевые факты.
Пользователь: {user_msg}
Ассистент: {assistant_msg}
Ответь ТОЛЬКО в формате JSON: [{{"content": "...", "type": "fact", "importance": 0.5}}]"""

        try:
            # Теперь вызываем асинхронно
            res = await self.llm.generate([{"role": "user", "content": prompt}], max_tokens=512)
            content = res.get("content", "").strip()

            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.error(f"Fact extraction failed: {e}")

        return []
