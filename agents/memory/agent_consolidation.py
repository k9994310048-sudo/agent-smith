"""
Модуль консолидации памяти для Agent Smith.
Управляет "забыванием" и объединением фактов.
"""
import logging
import math
from datetime import datetime

logger = logging.getLogger(__name__)

class MemoryConsolidation:
    def __init__(self, ikkf_bridge):
        self.ikkf = ikkf_bridge

    def decay_importance(self, initial_importance: float, created_at_iso: str) -> float:
        """
        Рассчитать текущую важность с учетом времени (экспоненциальное затухание).
        """
        try:
            created_at = datetime.fromisoformat(created_at_iso)
            days_passed = (datetime.now() - created_at).days

            # Коэффициент затухания: важность падает на 10% каждые 30 дней
            decay_rate = 0.003  # ~10% за месяц
            effective_importance = initial_importance * math.exp(-decay_rate * days_passed)

            return round(effective_importance, 2)
        except:
            return initial_importance

    def run_cleanup(self):
        """
        Базовая очистка: если факт стал совсем неважным, его можно архивировать.
        В данной реализации мы просто логируем или готовим данные для IKKF.
        """
        # В будущем здесь будет вызов IKKF API для массового обновления весов
        logger.info("Memory consolidation: cleanup cycle started")
        pass
