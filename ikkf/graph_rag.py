#!/usr/bin/env python3
"""
IKKF — RAG через граф знаний

Полный пайплайн:
  1. Вопрос пользователя
  2. Извлечение ключевых слов/сущностей
  3. Поиск начальных узлов (text + vector)
  4. Расширение контекста (BFS по графу)
  5. Ранжирование узлов по релевантности
  6. Формирование контекста для LLM
  7. Ответ LLM с контекстом

Запуск: python3 -m graph.graph_rag
"""

import os
import sys
import json
from typing import Optional
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from .graph import Graph
from .node import Node


class GraphRAG:
    """Retrieval-Augmented Generation через граф знаний."""

    def __init__(self, graph: Graph, embedding_model=None, llm_client=None):
        self.graph = graph
        self.embedding_model = embedding_model  # sentence-transformers model
        self.llm_client = llm_client  # функция/объект для вызова LLM

    def query(
        self,
        question: str,
        max_context_nodes: int = 10,
        max_depth: int = 2,
        min_weight: float = 0.3,
        project: str = None,
    ) -> dict:
        """
        Полный RAG пайплайн.

        Returns:
            {
                "question": str,
                "context_nodes": list[dict],
                "context_text": str,
                "answer": str (если llm_client задан),
                "stats": dict,
            }
        """
        # 1. Поиск начальных узлов
        seed_nodes = self._find_seed_nodes(question, project=project)

        # 2. Расширение контекста через граф
        expanded = self._expand_context(seed_nodes, max_depth=max_depth, min_weight=min_weight)

        # 3. Ранжирование
        ranked = self._rank_nodes(question, expanded, max_context_nodes)

        # 4. Формирование текста контекста
        context_text = self._build_context_text(ranked)

        result = {
            "question": question,
            "context_nodes": [{k: v for k, v in n.to_dict().items() if k != "embedding"} for n in ranked],
            "context_text": context_text,
            "stats": {
                "seeds_found": len(seed_nodes),
                "expanded_count": len(expanded),
                "final_count": len(ranked),
            },
        }

        # 5. Ответ LLM (если задан)
        if self.llm_client:
            result["answer"] = self._ask_llm(question, context_text)

        return result

    def _find_seed_nodes(self, question: str, project: str = None, limit: int = 10) -> list[Node]:
        """Найти начальные узлы по вопросу. Гибридный поиск: Vector similarity + FTS5.

        Приоритет: vector search (семантическая релевантность) > FTS5 (ключевые слова) > LIKE fallback.
        Фильтрует мусор: узлы из hermes-session, conversation-log, test проектов.
        """
        seeds = []
        seen = set()
        import re

        # Проекты-мусор которые нужно исключать из seed
        EXCLUDE_PROJECTS = {'hermes-session', 'conversation-log', 'test', 'hermes-memory'}

        def _add_node(node, score):
            if node and node.id not in seen and node.status == 'active':
                if node.project not in EXCLUDE_PROJECTS:
                    seen.add(node.id)
                    node._fts_score = score
                    seeds.append(node)

        # 1. Vector search — ПРИОРИТЕТНЫЙ (семантическая релевантность)
        try:
            from fastembed import TextEmbedding
            storage = self.graph.storage
            if not hasattr(storage, '_embed_model') or storage._embed_model is None:
                storage._embed_model = TextEmbedding(
                    model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
                )
            query_emb = list(storage._embed_model.embed([question]))[0]

            # Берём больше результатов чтобы после фильтрации осталось достаточно
            fast_results = storage.vector_search_fast(query_emb, limit=limit * 2, min_score=0.3)
            for r in fast_results:
                node = self.graph.get_node(r["node_id"])
                _add_node(node, r["score"])
        except Exception:
            pass

        # 2. FTS5 AND поиск (все значимые слова должны быть)
        words = re.findall(r'[а-яА-ЯёЁ]{2,}|[a-zA-Z0-9]{3,}', question.lower())
        stopwords = {
            'как', 'что', 'это', 'где', 'когда', 'почему', 'зачем', 'какой', 'какая', 'какие',
            'такое', 'который', 'которая', 'которые', 'такой', 'такая', 'такие',
            'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 'her', 'was',
            'one', 'our', 'out', 'has', 'have', 'been', 'were', 'they', 'them', 'than', 'that',
            'with', 'will', 'would', 'there', 'their', 'what', 'which', 'who', 'whom', 'how',
            'его', 'её', 'их', 'мой', 'твой', 'свой', 'наш', 'ваш', 'кто', 'чем', 'под',
            'над', 'при', 'про', 'без', 'для', 'или', 'так', 'еще', 'уже', 'тоже',
            'очень', 'более', 'менее', 'самый', 'только', 'даже', 'вот', 'этот',
            'is', 'it', 'to', 'of', 'in', 'on', 'at', 'by', 'an', 'be', 'do', 'if', 'no',
            'so', 'up', 'go', 'get', 'got',
        }
        words = [w for w in words if w not in stopwords and len(w) >= 2]

        if words and len(seeds) < limit:
            # AND поиск — все слова должны присутствовать (более строгий)
            and_query = ' AND '.join(words[:4])
            try:
                fts_results = self.graph.storage.search_nodes_fts_ranked(and_query, limit=limit)
                for row in fts_results:
                    node = self.graph.get_node(row["node_id"])
                    raw_rank = row.get("rank", 0)
                    score = 1.0 / (1.0 + abs(raw_rank))
                    _add_node(node, score * 0.9)  # чуть ниже приоритет чем vector
            except Exception:
                pass

            # Если AND ничего не нашёл — пробуем OR с ограничением
            if len(seeds) < 2:
                or_query = ' OR '.join(words[:4])
                try:
                    fts_results = self.graph.storage.search_nodes_fts_ranked(or_query, limit=limit)
                    for row in fts_results:
                        node = self.graph.get_node(row["node_id"])
                        raw_rank = row.get("rank", 0)
                        score = 1.0 / (1.0 + abs(raw_rank))
                        _add_node(node, score * 0.7)  # ещё ниже приоритет
                except Exception:
                    pass

        # 3. LIKE fallback (если вообще ничего не нашли)
        if len(seeds) < 2:
            like_results = self.graph.search_text(question, limit=limit)
            for n in like_results:
                _add_node(n, 0.3)

        # Фильтр по проекту
        if project:
            seeds = [n for n in seeds if n.project == project]

        return seeds[:limit]

    def _expand_context(self, seed_nodes: list[Node], max_depth: int = 2, min_weight: float = 0.3) -> list[dict]:
        """Расширить контекст через BFS от начальных узлов."""
        expanded = []
        visited = set()

        for seed in seed_nodes:
            visited.add(seed.id)
            expanded.append({
                "node": seed,
                "depth": 0,
                "source": "seed",
                "weight": 1.0,
            })

            # BFS от каждого seed
            bfs_results = self.graph.bfs(seed.id, max_depth=max_depth, min_weight=min_weight)
            for r in bfs_results:
                nid = r["node"]["id"]
                if nid not in visited:
                    visited.add(nid)
                    node = self.graph.get_node(nid)
                    if node:
                        expanded.append({
                            "node": node,
                            "depth": r["depth"],
                            "source": r["edge"]["edge_type"],
                            "weight": r["edge"]["weight"],
                        })

        return expanded

    def _rank_nodes(self, question: str, expanded: list[dict], max_nodes: int) -> list[Node]:
        """Ранжировать узлы по релевантности. Учитывает FTS5 rank, глубину, важность."""
        scored = []

        for item in expanded:
            node = item["node"]
            score = 0.0

            # 1. FTS5 rank (bm25) — самый важный фактор
            fts_score = getattr(node, '_fts_score', 0.5)
            score += fts_score * 0.35

            # 2. Глубина: чем ближе к seed, тем лучше
            depth_score = 1.0 / (1 + item["depth"])
            score += depth_score * 0.25

            # 3. Важность узла
            score += node.importance * 0.2

            # 4. Вес связи
            score += item["weight"] * 0.1

            # 5. Частота доступа
            access_score = min(1.0, node.access_count / 10.0)
            score += access_score * 0.05

            # 6. Seed бонус
            if item["source"] == "seed":
                score += 0.05

            scored.append((score, node))

        scored.sort(key=lambda x: x[0], reverse=True)

        seen = set()
        result = []
        for score, node in scored:
            if node.id not in seen:
                seen.add(node.id)
                result.append(node)
                if len(result) >= max_nodes:
                    break

        return result

    def _build_context_text(self, nodes: list[Node]) -> str:
        """Построить текстовый контекст для LLM."""
        if not nodes:
            return ""

        lines = ["=== Контекст из графа знаний ===\n"]
        for i, node in enumerate(nodes, 1):
            lines.append(f"{i}. [{node.node_type}] {node.content}")
            if node.tags:
                lines.append(f"   Теги: {', '.join(node.tags)}")
            if node.context.get("temporal"):
                lines.append(f"   Когда: {node.context['temporal']}")
            if node.context.get("semantic"):
                lines.append(f"   Тема: {node.context['semantic']}")
            lines.append("")

        return "\n".join(lines)

    def _ask_llm(self, question: str, context_text: str) -> str:
        """Задать вопрос LLM с контекстом."""
        prompt = f"""{context_text}

=== Вопрос ===
{question}

Ответь на вопрос, используя только информацию из контекста выше.
Если в контексте нет ответа, скажи честно что не знаешь."""

        if callable(self.llm_client):
            return self.llm_client(prompt)
        return "LLM client не настроен"

    def add_from_text(
        self,
        text: str,
        source: str = "conversation",
        project: str = "default",
        auto_link: bool = True,
    ) -> list[Node]:
        """
        Добавить информацию из текста в граф.
        Разбивает на предложения, создаёт узлы, связывает их.
        """
        import re

        # Разбить на предложения
        sentences = re.split(r'[.!?]\s+', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 10]

        nodes = []
        for sent in sentences:
            node = self.graph.add_node(
                content=sent,
                node_type="fact",
                source=source,
                project=project,
                importance=0.5,
                auto_embed=True,  # генерировать embedding при создании
            )
            nodes.append(node)

        # Связать соседние предложения
        if auto_link and len(nodes) > 1:
            for i in range(len(nodes) - 1):
                self.graph.add_edge(
                    nodes[i].id,
                    nodes[i + 1].id,
                    edge_type="sequence",
                    weight=0.5,
                )

        # Связать похожие (через текстовый поиск)
        if auto_link and len(nodes) > 2:
            for node in nodes:
                similar = self.graph.search_text(node.content[:50], limit=3)
                for sim in similar:
                    if sim.id != node.id:
                        # Проверяем что связи ещё нет
                        existing = self.graph.storage.get_neighbors(node.id)
                        existing_ids = {n["node"]["id"] for n in existing}
                        if sim.id not in existing_ids:
                            self.graph.add_edge(
                                node.id,
                                sim.id,
                                edge_type="similarity",
                                weight=0.4,
                            )

        return nodes


# ---- Тесты ----

if __name__ == "__main__":
    import tempfile

    print("=== Тест GraphRAG ===")
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    g = Graph(db_path)
    rag = GraphRAG(g)

    # Добавляем данные
    print("\n1. Добавляем данные в граф...")
    nodes = rag.add_from_text(
        "User works with AI Agent. "
        "OWL разработан компанией ZOO. IKKF — это модуль памяти для Hermes. "
        "IKKF хранит знания в виде графа. Граф состоит из узлов и связей.",
        source="test",
        project="test",
    )
    print(f"   Создано {len(nodes)} узлов")

    # Добавляем важные узлы вручную
    n1 = g.add_node("Test user - developer", node_type="entity", importance=0.9, project="test")
    n2 = g.add_node("MacBook Pro 2012 с Ubuntu 24.04", node_type="entity", importance=0.8, project="test")
    g.add_edge(n1.id, n2.id, "associative", 0.7)

    # Запрос
    print("\n2. Выполняем RAG запрос...")
    result = rag.query("Who is the user?", max_context_nodes=5)
    print(f"   Вопрос: {result['question']}")
    print(f"   Seeds: {result['stats']['seeds_found']}")
    print(f"   Expanded: {result['stats']['expanded_count']}")
    print(f"   Final: {result['stats']['final_count']}")
    print(f"\n   Контекст:\n{result['context_text'][:500]}")

    # Ещё запрос
    print("\n3. Запрос про IKKF...")
    result2 = rag.query("Что такое IKKF?", max_context_nodes=5)
    print(f"   Контекст:\n{result2['context_text'][:400]}")

    # Статистика
    print("\n4. Статистика графа:")
    stats = g.stats()
    print(f"   Узлов: {stats['nodes_active']}")
    print(f"   Связей: {stats['edges_total']}")
    print(f"   По типам: {stats['by_type']}")

    g.close()
    os.unlink(db_path)
    print("\n=== Все тесты GraphRAG пройдены ===")
