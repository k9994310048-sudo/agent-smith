#!/usr/bin/env python3
"""
IKKF — Интеграция старого поиска (ChromaDB) с новым (Graph)

При поиске через старый IKKF API (порт 8765):
1. Ищем через ChromaDB (старый векторный поиск)
2. Ищем через Graph (новый графовый поиск + BFS расширение)
3. Объединяем и ранжируем результаты

Запуск: python3 -m graph.integration
"""

import os
import sys
import json
import requests
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from graph.graph import Graph
from graph.graph_rag import GraphRAG


class IKKFIntegration:
    """Интеграция старого IKKF с новым Graph."""

    def __init__(self, graph: Graph = None):
        self.graph = graph or Graph()
        self.rag = GraphRAG(self.graph)
        self.old_api = "http://127.0.0.1:8765"
        self.graph_api = "http://127.0.0.1:8766"

    def hybrid_search(
        self,
        query: str,
        project_id: str = None,
        limit: int = 10,
        use_graph: bool = True,
        use_old: bool = True,
        graph_depth: int = 2,
    ) -> dict:
        """
        Гибридный поиск: старый IKKF + граф.

        Returns:
            {
                "query": str,
                "results": list[dict],
                "sources": {"old": int, "graph": int, "merged": int},
            }
        """
        all_results = {}  # chunk_id -> result

        # 1. Старый поиск (ChromaDB)
        if use_old:
            try:
                old_results = self._search_old(query, project_id, limit=limit)
                for r in old_results:
                    rid = r.get("chunk_id", r.get("id", ""))
                    all_results[rid] = {
                        "id": rid,
                        "content": r.get("content", ""),
                        "score": r.get("score", 0) * 0.5,  # вес старого поиска
                        "source": "old_ikkf",
                        "project": r.get("project", ""),
                    }
            except Exception as e:
                print(f"Old IKKF search error: {e}")

        # 2. Графовый поиск
        if use_graph:
            try:
                graph_results = self._search_graph(query, project_id, limit=limit, depth=graph_depth)
                for r in graph_results:
                    rid = r.get("id", "")
                    if rid in all_results:
                        # Уже есть из старого — усиливаем
                        all_results[rid]["score"] += r.get("score", 0) * 0.5
                        all_results[rid]["source"] = "both"
                    else:
                        all_results[rid] = {
                            "id": rid,
                            "content": r.get("content", ""),
                            "score": r.get("score", 0) * 0.5,
                            "source": "graph",
                            "project": r.get("project", ""),
                        }
            except Exception as e:
                print(f"Graph search error: {e}")

        # 3. Сортировка
        sorted_results = sorted(all_results.values(), key=lambda x: x["score"], reverse=True)

        # 4. Статистика
        sources = {"old": 0, "graph": 0, "both": 0}
        for r in sorted_results:
            s = r.get("source", "")
            if s in sources:
                sources[s] += 1

        return {
            "query": query,
            "results": sorted_results[:limit],
            "sources": {
                "old": sources["old"],
                "graph": sources["graph"],
                "both": sources["both"],
                "merged": len(sorted_results),
            },
        }

    def _search_old(self, query: str, project_id: str = None, limit: int = 10) -> list[dict]:
        """Поиск через старый IKKF API."""
        payload = {"query": query, "limit": limit}
        if project_id:
            payload["project_id"] = project_id

        resp = requests.post(f"{self.old_api}/search", json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])

    def _search_graph(self, query: str, project_id: str = None, limit: int = 10, depth: int = 2) -> list[dict]:
        """Поиск через граф с расширением."""
        # Используем RAG для поиска
        rag_result = self.rag.query(
            query,
            max_context_nodes=limit,
            max_depth=depth,
            project=project_id.replace("project_", "") if project_id else None,
        )

        results = []
        for node_dict in rag_result.get("context_nodes", []):
            results.append({
                "id": node_dict.get("id", ""),
                "content": node_dict.get("content", ""),
                "score": node_dict.get("importance", 0.5),
                "project": node_dict.get("project", ""),
                "node_type": node_dict.get("node_type", ""),
            })

        return results

    def close(self):
        self.graph.close()


# ---- Тесты ----

if __name__ == "__main__":
    print("=== Тест интеграции IKKF ===")

    integ = IKKFIntegration()

    # Тест 1: Гибридный поиск
    print("\n1. Гибридный поиск 'Hermes':")
    result = integ.hybrid_search("Hermes", limit=5)
    print(f"   Найдено: {result['sources']}")
    for r in result["results"][:3]:
        print(f"   [{r['source']}] score={r['score']:.3f} | {r['content'][:60]}")

    # Тест 2: Поиск по проекту
    print("\n2. Поиск по проекту 'i-know-kung-fu':")
    result = integ.hybrid_search("IKKF модуль", project_id="project_i-know-kung-fu", limit=5)
    print(f"   Найдено: {result['sources']}")
    for r in result["results"][:3]:
        print(f"   [{r['source']}] score={r['score']:.3f} | {r['content'][:60]}")

    # Тест 3: Только граф
    print("\n3. Только графовый поиск:")
    result = integ.hybrid_search("test_query", use_old=False, limit=5)
    print(f"   Найдено: {result['sources']}")

    integ.close()
    print("\n=== Тест интеграции завершён ===")
