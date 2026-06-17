"""
IKKF — Graph (основной класс графа знаний)

Объединяет Node, Edge, Storage в единую систему.
Реализует:
- Добавление узлов и связей
- Поиск по графу (BFS/DFS)
- Векторный поиск (через embedding)
- Контекстный поиск (по измерениям)
- Предиктивную подгрузку
"""

import heapq
from datetime import datetime
from typing import Optional

from .node import Node, Edge, CONTEXT_DIMS, NODE_TYPES, EDGE_TYPES
from .storage import Storage


class Graph:
    """Граф знаний IKKF."""

    def __init__(self, db_path: str = None):
        self.storage = Storage(db_path)
        # L1: RAM кэш (горячие узлы)
        self._cache: dict[str, Node] = {}
        self._cache_max = 1000

    # ---- Узлы ----

    def add_node(
        self,
        content: str,
        node_type: str = "fact",
        embedding: list = None,
        context: dict = None,
        importance: float = 0.5,
        tags: list = None,
        source: str = "api",
        project: str = "default",
        verified: int = 0,
        auto_embed: bool = False,
        auto_link: bool = True,
    ) -> Node:
        """Создать и сохранить узел. Опционально автосвязывание с похожими."""
        node = Node(
            content=content,
            node_type=node_type,
            embedding=embedding,
            context=context,
            importance=importance,
            tags=tags,
            source=source,
            project=project,
            verified=verified,
        )
        self.storage.save_node(node, auto_embed=auto_embed)
        self._cache_node(node)

        # Contradiction check for facts
        if node.node_type == "fact" and node.verified == 0:
            contradictions = self._check_contradictions(node)
            if contradictions:
                node.metadata["contradictions"] = contradictions
                self.storage.save_node(node, auto_embed=False)

        # Автосвязывание с похожими узлами
        if auto_link and content and len(content) > 10:
            self._auto_link_node(node)

        return node

    def _auto_link_node(self, node: Node, max_links: int = 5, min_jaccard: float = 0.15):
        """Найти похожие узлы и создать связи associative."""
        import re
        words = set(re.findall(r'[а-яА-ЯёЁa-zA-Z0-9]{3,}', node.content.lower()))
        if len(words) < 2:
            return

        # Ищем кандидатов через FTS5 OR
        or_query = ' OR '.join(list(words)[:6])
        try:
            candidates = self.storage.search_nodes_fts_ranked(or_query, limit=20)
        except Exception:
            return

        links_created = 0
        for cand in candidates:
            if links_created >= max_links:
                break
            other_id = cand["node_id"]
            if other_id == node.id:
                continue
            # Проверяем что связи ещё нет
            existing = self.storage.get_neighbors(node.id)
            existing_ids = {n["node"]["id"] for n in existing}
            if other_id in existing_ids:
                continue

            other = self.storage.get_node(other_id)
            if not other or other.status != "active":
                continue

            # Jaccard similarity
            other_words = set(re.findall(r'[а-яА-ЯёЁa-zA-Z0-9]{3,}', other.content.lower()))
            if not other_words:
                continue
            intersection = words & other_words
            union = words | other_words
            jaccard = len(intersection) / len(union) if union else 0

            if jaccard >= min_jaccard:
                weight = min(0.9, max(0.3, jaccard))
                self.add_edge(node.id, other_id, "associative", weight)
                links_created += 1

    def _check_contradictions(self, new_node, threshold=0.85, top_k=20):
        """Check if new fact contradicts existing facts via embedding similarity."""
        try:
            import numpy as np
            new_emb = new_node.embedding
            if new_emb is None or len(new_emb) == 0:
                return []
            new_emb = np.array(new_emb)
            # Get recent fact nodes
            rows = self.storage.conn.execute(
                "SELECT id, content, embedding FROM nodes WHERE node_type='fact' AND id != ? ORDER BY created_at DESC LIMIT ?",
                (new_node.id, top_k)
            ).fetchall()
            contradictions = []
            for row in rows:
                if row[2] is None:
                    continue
                try:
                    emb = np.array(__import__("json").loads(row[2]))
                except:
                    continue
                sim = float(np.dot(new_emb, emb) / (np.linalg.norm(new_emb) * np.linalg.norm(emb)))
                # High similarity but different content = potential contradiction
                if sim > threshold and row[1] != new_node.content:
                    contradictions.append({
                        "node_id": row[0],
                        "content": row[1][:100],
                        "similarity": round(sim, 3)
                    })
            return contradictions[:3]  # max 3 contradictions
        except Exception:
            return []

    def get_node(self, node_id: str) -> Optional[Node]:
        """Получить узел (сначала из кэша, потом из БД)."""
        if node_id in self._cache:
            self._cache[node_id].touch()
            return self._cache[node_id]
        node = self.storage.get_node(node_id)
        if node:
            node.touch()
            self._cache_node(node)
        return node

    def update_node(self, node_id: str, **kwargs) -> Optional[Node]:
        """Обновить поля узла. При смене content — автоматически сохраняет старую версию в history."""
        node = self.get_node(node_id)
        if not node:
            return None
        new_content = kwargs.pop("content", None)
        if new_content is not None and new_content != node.content:
            reason = kwargs.pop("reason", "")
            node.update_content(new_content, reason=reason)
        for k, v in kwargs.items():
            if hasattr(node, k):
                setattr(node, k, v)
        node.updated_at = datetime.utcnow().isoformat()
        self.storage.save_node(node)
        self._cache_node(node)
        return node

    def delete_node(self, node_id: str) -> bool:
        """Удалить узел и все его связи."""
        self._cache.pop(node_id, None)
        return self.storage.delete_node(node_id)

    # ---- Связи ----

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str = "semantic",
        weight: float = 0.5,
        bidirectional: bool = False,
    ) -> Optional[Edge]:
        """Создать связь между узлами."""
        # Проверяем что оба узла существуют
        if not self.storage.get_node(source_id) or not self.storage.get_node(target_id):
            return None
        edge = Edge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            weight=weight,
            bidirectional=bidirectional,
        )
        self.storage.save_edge(edge)
        return edge

    def get_neighbors(self, node_id: str, **kwargs) -> list[dict]:
        """Получить соседей узла."""
        return self.storage.get_neighbors(node_id, **kwargs)

    def strengthen_edge(self, edge_id: str, delta: float = 0.1):
        """Усилить связь."""
        edge = self.storage.get_edge(edge_id)
        if edge:
            edge.strengthen(delta)
            self.storage.save_edge(edge)

    # ---- Поиск ----

    def search_text(self, query: str, limit: int = 20) -> list[Node]:
        """Полнотекстовый поиск по content."""
        return self.storage.search_nodes_text(query, limit)

    def bfs(self, start_id: str, max_depth: int = 3, min_weight: float = 0.3) -> list[dict]:
        """Поиск в ширину от начального узла."""
        visited = {start_id}
        queue = [(start_id, 0)]
        results = []

        while queue:
            current_id, depth = queue.pop(0)
            if depth >= max_depth:
                continue

            neighbors = self.storage.get_neighbors(current_id, min_weight=min_weight)
            for n in neighbors:
                neighbor_id = n["node"]["id"]
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    queue.append((neighbor_id, depth + 1))
                    results.append({
                        "node": n["node"],
                        "edge": n["edge"],
                        "depth": depth + 1,
                        "direction": n["direction"],
                    })

        return results

    def dfs(self, start_id: str, max_depth: int = 3, min_weight: float = 0.3) -> list[dict]:
        """Поиск в глубину от начального узла."""
        visited = {start_id}
        results = []

        def _dfs(node_id, depth):
            if depth >= max_depth:
                return
            neighbors = self.storage.get_neighbors(node_id, min_weight=min_weight)
            for n in neighbors:
                neighbor_id = n["node"]["id"]
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    results.append({
                        "node": n["node"],
                        "edge": n["edge"],
                        "depth": depth + 1,
                        "direction": n["direction"],
                    })
                    _dfs(neighbor_id, depth + 1)

        _dfs(start_id, 0)
        return results

    def find_path(self, from_id: str, to_id: str, max_depth: int = 5) -> list[dict]:
        """Найти путь между узлами (BFS)."""
        if from_id == to_id:
            return []

        visited = {from_id}
        queue = [(from_id, [])]

        while queue:
            current_id, path = queue.pop(0)
            if len(path) >= max_depth:
                continue

            neighbors = self.storage.get_neighbors(current_id)
            for n in neighbors:
                neighbor_id = n["node"]["id"]
                new_path = path + [n]
                if neighbor_id == to_id:
                    return new_path
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    queue.append((neighbor_id, new_path))

        return []  # Путь не найден

    def context_search(self, **dimensions) -> list[Node]:
        """Поиск по контексту (измерениям)."""
        # Строим SQL запрос по измерениям
        # Пример: context_search(temporal="2026-06", semantic="разработка")
        all_nodes = self.storage.list_nodes(limit=10000)
        results = []

        for node in all_nodes:
            match = True
            for dim, value in dimensions.items():
                if dim not in CONTEXT_DIMS:
                    continue
                node_val = node.context.get(dim)
                if node_val is None or str(value).lower() not in str(node_val).lower():
                    match = False
                    break
            if match:
                results.append(node)

        results.sort(key=lambda n: n.importance, reverse=True)
        return results

    def vector_search(self, query_embedding: list, limit: int = 20, project: str = None) -> list[dict]:
        """
        Векторный поиск по embeddings узлов.
        Использует sqlite-vec (HNSW) если доступен, иначе brute-force fallback.
        """
        # Use fast sqlite-vec search
        fast_results = self.storage.vector_search_fast(query_embedding, limit=limit * 2, min_score=0.1)

        results = []
        for r in fast_results:
            node = self.storage.get_node(r["node_id"])
            if node and node.status == "active":
                if project and node.project != project:
                    continue
                results.append({"node": node, "score": r["score"]})

        return results[:limit]

    def get_important_nodes(self, limit: int = 20, project: str = None) -> list[Node]:
        """Получить самые важные узлы."""
        return self.storage.list_nodes(project=project, limit=limit)

    def get_recent_nodes(self, limit: int = 20, project: str = None) -> list[Node]:
        """Получить последние узлы."""
        nodes = self.storage.list_nodes(project=project, limit=limit)
        nodes.sort(key=lambda n: n.created_at, reverse=True)
        return nodes

    # ---- Предиктивная подгрузка ----

    def predict_related(self, node_id: str, limit: int = 10) -> list[dict]:
        """Предсказать связанные узлы (2 хопа + сортировка по весу)."""
        # 1 хоп — прямые соседи
        direct = self.storage.get_neighbors(node_id)
        direct_ids = {n["node"]["id"] for n in direct}

        # 2 хоп — соседи соседей
        indirect = []
        for n in direct:
            nid = n["node"]["id"]
            for n2 in self.storage.get_neighbors(nid):
                n2id = n2["node"]["id"]
                if n2id != node_id and n2id not in direct_ids:
                    indirect.append({
                        "node": n2["node"],
                        "edge": n2["edge"],
                        "depth": 2,
                        "via": nid,
                        "score": n["edge"]["weight"] * n2["edge"]["weight"],
                    })

        # Сортировка по score
        indirect.sort(key=lambda x: x["score"], reverse=True)
        return indirect[:limit]

    # ---- Статистика ----

    def stats(self) -> dict:
        return self.storage.get_stats()

    # ---- Обслуживание ----

    def consolidate(self, full: bool = True):
        """Ночная консолидация: архивация, объединение дубликатов, оптимизация."""
        from consolidation import Consolidator
        c = Consolidator(self)
        stats = c.run(full=full)
        return stats

    def close(self):
        self.storage.close()

    # ---- Semantic Cache ----

    def check_cache(self, query: str) -> Optional[str]:
        return self.storage.get_cache(query)

    def store_cache(self, query: str, response: str):
        self.storage.save_cache(query, response)

    # ---- Кэш ----

    def _cache_node(self, node: Node):
        """Положить узел в L1 кэш."""
        if len(self._cache) >= self._cache_max:
            # Удаляем наименее важный
            min_key = min(self._cache, key=lambda k: self._cache[k].importance)
            del self._cache[min_key]
        self._cache[node.id] = node


# ---- Тесты ----

if __name__ == "__main__":
    import tempfile
    import os

    print("=== Тест Graph ===")
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    g = Graph(db_path)

    # Создаём узлы
    n1 = g.add_node("User works with AI Agent", node_type="fact", importance=0.9, project="test")
    n2 = g.add_node("Hermes — AI агент", node_type="concept", importance=0.8, project="test")
    n3 = g.add_node("IKKF — модуль памяти", node_type="concept", importance=0.85, project="test")
    n4 = g.add_node("OWL — модель от ZOO", node_type="entity", importance=0.7, project="test")
    print(f"Создано 4 узла")

    # Связи
    g.add_edge(n1.id, n2.id, "semantic", 0.9)
    g.add_edge(n2.id, n3.id, "associative", 0.8)
    g.add_edge(n3.id, n4.id, "semantic", 0.7)
    g.add_edge(n1.id, n3.id, "contextual", 0.6)
    print(f"Создано 4 связи")

    # BFS
    bfs_results = g.bfs(n1.id, max_depth=2)
    print(f"BFS от n1: {len(bfs_results)} узлов найдено")

    # Path
    path = g.find_path(n1.id, n4.id)
    print(f"Путь n1→n4: {len(path)} шагов")

    # Поиск по тексту
    found = g.search_text("Hermes")
    print(f"Поиск 'Hermes': {len(found)} результатов")

    # Важные узлы
    important = g.get_important_nodes(limit=3)
    print(f"Топ-3 важных: {[n.content[:30] for n in important]}")

    # Предиктивная подгрузка
    predicted = g.predict_related(n1.id)
    print(f"Предсказано связанных: {len(predicted)}")

    # Статистика
    stats = g.stats()
    print(f"Статистика: {stats}")

    g.close()
    os.unlink(db_path)
    print("\n=== Все тесты Graph пройдены ===")
