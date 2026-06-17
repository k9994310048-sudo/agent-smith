#!/usr/bin/env python3
"""
IKKF — Бенчмарки и тестирование

Тесты:
1. Производительность CRUD операций
2. Производительность поиска
3. Производительность обхода графа
4. Качество RAG
5. Потребление памяти
6. Размер БД

Запуск: python3 -m graph.benchmark
"""

import os
import sys
import time
import json
import tempfile
import statistics

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from graph.graph import Graph
from graph.graph_rag import GraphRAG
from graph.consolidation import Consolidator


def benchmark(func, *args, iterations=100, **kwargs):
    """Замерить время выполнения функции."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    return {
        "mean_ms": statistics.mean(times) * 1000,
        "median_ms": statistics.median(times) * 1000,
        "min_ms": min(times) * 1000,
        "max_ms": max(times) * 1000,
        "p95_ms": sorted(times)[int(len(times) * 0.95)] * 1000,
        "iterations": iterations,
    }


def run_benchmarks():
    """Запустить все бенчмарки."""
    print("=" * 60)
    print("IKKF — Бенчмарки производительности")
    print("=" * 60)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    g = Graph(db_path)
    rag = GraphRAG(g)

    results = {}

    # ---- 1. CRUD ----
    print("\n--- 1. CRUD операции ---")

    # Create
    node_ids = []
    def create_node():
        n = g.add_node(f"Тестовый узел {len(node_ids)}", node_type="fact", importance=0.5, project="bench")
        node_ids.append(n.id)
        return n

    r = benchmark(create_node, iterations=100)
    results["create_node"] = r
    print(f"  Create: {r['mean_ms']:.2f}ms (median: {r['median_ms']:.2f}ms)")

    # Read
    def read_node():
        return g.get_node(node_ids[0]) if node_ids else None

    r = benchmark(read_node, iterations=100)
    results["read_node"] = r
    print(f"  Read:   {r['mean_ms']:.2f}ms (median: {r['median_ms']:.2f}ms)")

    # Update
    def update_node():
        return g.update_node(node_ids[0], importance=0.7) if node_ids else None

    r = benchmark(update_node, iterations=50)
    results["update_node"] = r
    print(f"  Update: {r['mean_ms']:.2f}ms (median: {r['median_ms']:.2f}ms)")

    # ---- 2. Поиск ----
    print("\n--- 2. Поиск ---")

    # Наполняем данными
    for i in range(50):
        g.add_node(f"Узел про {['AI_Agent', 'LLM', 'Graph', 'User', 'Linux'][i % 5]} номер {i}",
                   node_type=["fact", "concept", "entity"][i % 3],
                   importance=0.3 + (i % 7) * 0.1,
                   project="bench")

    def search_text():
        return g.search_text("Hermes", limit=10)

    r = benchmark(search_text, iterations=50)
    results["search_text"] = r
    print(f"  Text search: {r['mean_ms']:.2f}ms (median: {r['median_ms']:.2f}ms)")

    # ---- 3. Обход графа ----
    print("\n--- 3. Обход графа ---")

    # Создаём цепочку узлов
    chain_ids = []
    for i in range(20):
        n = g.add_node(f"Цепочка узел {i}", node_type="fact", project="chain")
        chain_ids.append(n.id)
        if i > 0:
            g.add_edge(chain_ids[i-1], chain_ids[i], "sequence", 0.8)

    def bfs_traversal():
        return g.bfs(chain_ids[0], max_depth=5)

    r = benchmark(bfs_traversal, iterations=20)
    results["bfs"] = r
    print(f"  BFS (depth=5): {r['mean_ms']:.2f}ms (median: {r['median_ms']:.2f}ms)")

    def find_path():
        return g.find_path(chain_ids[0], chain_ids[-1])

    r = benchmark(find_path, iterations=20)
    results["find_path"] = r
    print(f"  Path (20 nodes): {r['mean_ms']:.2f}ms (median: {r['median_ms']:.2f}ms)")

    # ---- 4. RAG ----
    print("\n--- 4. RAG ---")

    def rag_query():
        return rag.query("Что такое Hermes?", max_context_nodes=5)

    r = benchmark(rag_query, iterations=10)
    results["rag_query"] = r
    print(f"  RAG query: {r['mean_ms']:.2f}ms (median: {r['median_ms']:.2f}ms)")

    # ---- 5. Консолидация ----
    print("\n--- 5. Консолидация ---")

    # Создаём дубликаты
    for i in range(10):
        g.add_node("Дубликат тестового узла", node_type="fact", importance=0.5, project="bench")

    c = Consolidator(g)

    start = time.perf_counter()
    c.run(full=True)
    consolidation_time = (time.perf_counter() - start) * 1000
    results["consolidation"] = {"total_ms": consolidation_time}
    print(f"  Consolidation: {consolidation_time:.2f}ms")

    # ---- 6. Статистика ----
    print("\n--- 6. Статистика графа ---")
    stats = g.stats()
    results["stats"] = stats
    print(f"  Узлов: {stats['nodes_active']}")
    print(f"  Связей: {stats['edges_total']}")
    print(f"  Размер БД: {stats['db_size_mb']} MB")
    print(f"  По типам: {stats['by_type']}")

    # ---- Итог ----
    print("\n" + "=" * 60)
    print("ИТОГО")
    print("=" * 60)
    print(json.dumps(results, indent=2, ensure_ascii=False))

    g.close()
    os.unlink(db_path)

    return results


if __name__ == "__main__":
    run_benchmarks()
