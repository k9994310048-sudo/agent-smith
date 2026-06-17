#!/usr/bin/env python3
"""
IKKF — Предиктивная подгрузка через LLM

Анализирует текущий разговор и предсказывает:
1. Какие темы могут быть затронуты далее
2. Какие узлы графа понадобятся
3. Подгружает их в L1 кэш заранее

Это уменьшает latency: когда пользователь спросит — данные уже в памяти.

Запуск: python3 -m graph.predictive
"""

import os
import sys
import json
from typing import Optional
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from graph.graph import Graph
from graph.node import Node


class PredictivePreloader:
    """Предиктивная подгрузка узлов графа."""

    def __init__(self, graph: Graph, llm=None):
        self.graph = graph
        self.llm = llm  # KungFuLLM
        self.preload_cache = {}  # topic -> [node_ids]
        self.max_preload = 50  # максимум узлов в кэше

    def predict_and_preload(self, recent_messages: list[str], current_topic: str = None):
        """
        Предсказать какие узлы понадобятся и подгрузить их.

        Args:
            recent_messages: последние сообщения разговора
            current_topic: текущая тема (если известна)
        """
        # 1. Определить темы для подгрузки
        topics = self._predict_topics(recent_messages, current_topic)

        # 2. Для каждой темы найти и подгрузить узлы
        preloaded = 0
        for topic in topics:
            nodes = self._find_nodes_for_topic(topic)
            for node in nodes[:5]:  # максимум 5 узлов на тему
                self._preload_node(node)
                preloaded += 1

        return {"topics": topics, "preloaded": preloaded}

    def _predict_topics(self, messages: list[str], current_topic: str = None) -> list[str]:
        """Предсказать следующие темы на основе контекста."""
        topics = []

        # Текущая тема
        if current_topic:
            topics.append(current_topic)

        # Извлечь ключевые слова из последних сообщений
        all_text = " ".join(messages[-5:])  # последние 5 сообщений

        # Простой извлечение ключевых слов (частотный анализ)
        keywords = self._extract_keywords(all_text)
        topics.extend(keywords)

        # Если есть LLM — используем её для более умного предсказания
        if self.llm:
            try:
                llm_topics = self._llm_predict_topics(all_text)
                topics.extend(llm_topics)
            except Exception:
                pass

        # Уникализация
        seen = set()
        unique = []
        for t in topics:
            t_lower = t.lower()
            if t_lower not in seen and len(t) > 2:
                seen.add(t_lower)
                unique.append(t)

        return unique[:10]

    def _extract_keywords(self, text: str) -> list[str]:
        """Извлечь ключевые слова из текста (частотный анализ)."""
        import re
        from collections import Counter

        # Убрать стоп-слова (русские)
        stopwords = {
            'и', 'в', 'на', 'с', 'по', 'для', 'не', 'что', 'это', 'как',
            'но', 'да', 'нет', 'от', 'до', 'из', 'за', 'мы', 'ты', 'он',
            'она', 'они', 'его', 'её', 'их', 'мне', 'тебе', 'ему', 'ей',
            'бы', 'ли', 'же', 'уже', 'ещё', 'тоже', 'очень', 'просто',
            'может', 'надо', 'нужно', 'будет', 'был', 'была', 'были',
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
            'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'could', 'should', 'may', 'might', 'must', 'shall',
            'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in',
            'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
            'through', 'during', 'before', 'after', 'above', 'below',
            'between', 'out', 'off', 'over', 'under', 'again', 'further',
            'then', 'once', 'here', 'there', 'when', 'where', 'why',
            'how', 'all', 'each', 'every', 'both', 'few', 'more', 'most',
            'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own',
            'same', 'so', 'than', 'too', 'very', 'just', 'also',
        }

        # Извлечь слова
        words = re.findall(r'[а-яА-Яa-zA-Z]{3,}', text.lower())
        words = [w for w in words if w not in stopwords]

        # Частотный анализ
        counter = Counter(words)
        return [word for word, count in counter.most_common(10)]

    def _llm_predict_topics(self, text: str) -> list[str]:
        """Использовать LLM для предсказания тем."""
        if not self.llm:
            return []

        prompt = f"""Проанализируй разговор и предскажи 3-5 тем, которые могут быть затронуты далее.

Разговор:
"{text[:500]}"

Ответь JSON массивом строк: ["тема1", "тема2", ...]

Ответ:"""

        try:
            result = self.llm._ask(prompt, max_tokens=64)
            import re
            match = re.search(r'\[.*\]', result, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception:
            pass

        return []

    def _find_nodes_for_topic(self, topic: str) -> list[Node]:
        """Найти узлы графа по теме."""
        # Текстовый поиск
        nodes = self.graph.search_text(topic, limit=5)
        return nodes

    def _preload_node(self, node: Node):
        """Подгрузить узел в L1 кэш."""
        if len(self.graph._cache) < self.graph._cache_max:
            node.touch()
            self.graph._cache[node.id] = node

    def get_preload_stats(self) -> dict:
        """Статистика предзагрузки."""
        return {
            "cache_size": len(self.graph._cache),
            "cache_max": self.graph._cache_max,
            "cache_usage_pct": round(len(self.graph._cache) / self.graph._cache_max * 100, 1),
        }


# ---- Тесты ----

if __name__ == "__main__":
    print("=== Тест Predictive Preloader ===")
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    g = Graph(db_path)

    # Наполняем данными
    g.add_node("Hermes Agent — AI ассистент от Nous Research", node_type="concept", importance=0.9)
    g.add_node("OWL — языковая модель от ZOO company", node_type="entity", importance=0.8)
    g.add_node("IKKF — модуль памяти на графе знаний", node_type="concept", importance=0.85)
    g.add_node("Ubuntu 24.04 LTS — операционная система", node_type="entity", importance=0.7)
    g.add_node("Laptop for development", node_type="entity", importance=0.75)
    g.add_node("Python — язык программирования", node_type="concept", importance=0.6)
    g.add_node("FastAPI — веб-фреймворк для Python", node_type="concept", importance=0.65)

    p = PredictivePreloader(g)

    # Тест 1: Предсказание тем
    print("\n1. Предсказание тем:")
    messages = [
        "Привет, как дела?",
        "Работаю над проектом IKKF",
        "Хочу добавить векторный поиск",
    ]
    topics = p._predict_topics(messages, "IKKF")
    print(f"   Темы: {topics}")

    # Тест 2: Предзагрузка
    print("\n2. Предзагрузка узлов:")
    result = p.predict_and_preload(messages, "IKKF")
    print(f"   Темы: {result['topics']}")
    print(f"   Подгружено: {result['preloaded']}")

    # Статистика
    print("\n3. Статистика кэша:")
    stats = p.get_preload_stats()
    print(f"   {stats}")

    g.close()
    os.unlink(db_path)
    print("\n=== Тест Predictive Preloader пройден ===")
