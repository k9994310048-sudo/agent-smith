"""
IKKF — Node (узел графа знаний)

Типы узлов:
- fact       : факт (утверждение, которое можно проверить)
- concept    : концепция (идея, понятие, определение)
- action     : действие (что-то было сделано)
- entity     : сущность (человек, проект, инструмент)
- event      : событие (произошло в определённое время)
- skill      : навык/умение (как что-делать)
- project    : проект
- idea       : идея (предложение, мысль)

5 контекстуальных измерений:
- temporal   : когда? (дата, время, период)
- spatial    : где? (место, локация, контекст)
- semantic   : о чём? (тема, предметная область)
- emotional  : как? (настроение, тон, отношение)
- social     : кто? (участники, роли, отношения)
"""

import uuid
import json
from datetime import datetime
from typing import Optional


# ---- Константы ----

NODE_TYPES = ("fact", "concept", "action", "entity", "event", "skill", "project", "idea")

EDGE_TYPES = (
    "semantic",      # семантическая связь (похож по смыслу)
    "temporal",      # временная связь (до/после)
    "causal",        # причинно-следственная (вызывает/вызван)
    "associative",   # ассоциативная (связан в контексте)
    "hierarchical",  # иерархический (родитель/потомок)
    "contextual",    # контекстуальный (в том же контексте)
    "similarity",    # похожесть (векторная близость)
    "sequence",      # последовательность (шаг за шагом)
)

CONTEXT_DIMS = ("temporal", "spatial", "semantic", "emotional", "social")


# ---- Node ----

class Node:
    """Узел графа знаний."""

    def __init__(
        self,
        content: str,
        node_type: str = "fact",
        embedding: Optional[list] = None,
        context: Optional[dict] = None,
        metadata: Optional[dict] = None,
        importance: float = 0.5,
        tags: Optional[list] = None,
        node_id: Optional[str] = None,
        source: str = "api",
        project: str = "default",
        verified: int = 0,
    ):
        if node_type not in NODE_TYPES:
            raise ValueError(f"Неизвестный тип узла: {node_type}. Допустимые: {NODE_TYPES}")

        self.id: str = node_id or str(uuid.uuid4())
        self.content: str = content
        self.node_type: str = node_type
        self.embedding: Optional[list] = embedding
        self.context: dict = context or {d: None for d in CONTEXT_DIMS}
        self.metadata: dict = metadata or {}
        self.importance: float = max(0.0, min(1.0, importance))
        self.tags: list = tags or []
        self.source: str = source
        self.project: str = project
        self.verified: int = 1 if verified else 0
        self.access_count: int = 0
        self.status: str = "active"
        self.created_at: str = datetime.utcnow().isoformat()
        self.updated_at: str = self.created_at
        self.last_accessed: Optional[str] = None
        self.history: list = []  # [{"content": ..., "created": ..., "reason": ...}, ...]

    def touch(self):
        """Обновить время последнего доступа."""
        self.access_count += 1
        self.last_accessed = datetime.utcnow().isoformat()

    def update_importance(self, delta: float):
        """Изменить важность (от -1.0 до +1.0)."""
        self.importance = max(0.0, min(1.0, self.importance + delta))
        self.updated_at = datetime.utcnow().isoformat()

    def update_content(self, new_content: str, reason: str = ""):
        """Обновить содержимое с сохранением старой версии в history."""
        if new_content == self.content:
            return  # не записывать если ничего не изменилось
        self.history.append({
            "content": self.content,
            "created": self.updated_at,
            "reason": reason,
        })
        self.content = new_content
        self.updated_at = datetime.utcnow().isoformat()

    def set_summary(self, summary: str):
        """Установить краткую сводку для context compression."""
        self.metadata["summary"] = summary

    def get_summary(self, max_chars: int = 200) -> str:
        """Получить краткую сводку: из metadata или первые N символов."""
        if self.metadata.get("summary"):
            return self.metadata["summary"]
        # fallback: первые N символов
        if len(self.content) <= max_chars:
            return self.content
        return self.content[:max_chars].rsplit(" ", 1)[0] + "..."

    def set_context(self, dimension: str, value):
        """Установить значение контекстуального измерения."""
        if dimension not in CONTEXT_DIMS:
            raise ValueError(f"Неизвестное измерение: {dimension}. Допустимые: {CONTEXT_DIMS}")
        self.context[dimension] = value
        self.updated_at = datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "node_type": self.node_type,
            "embedding": self.embedding,
            "context": self.context,
            "metadata": self.metadata,
            "importance": self.importance,
            "tags": self.tags,
            "source": self.source,
            "project": self.project,
            "verified": self.verified,
            "access_count": self.access_count,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_accessed": self.last_accessed,
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Node":
        n = cls(
            content=data["content"],
            node_type=data.get("node_type", "fact"),
            embedding=data.get("embedding"),
            context=data.get("context"),
            metadata=data.get("metadata"),
            importance=data.get("importance", 0.5),
            tags=data.get("tags"),
            node_id=data.get("id"),
            source=data.get("source", "api"),
            project=data.get("project", "default"),
        )
        n.verified = data.get("verified", 0)
        n.access_count = data.get("access_count", 0)
        n.status = data.get("status", "active")
        n.created_at = data.get("created_at", n.created_at)
        n.updated_at = data.get("updated_at", n.updated_at)
        n.last_accessed = data.get("last_accessed")
        n.history = data.get("history", [])
        return n

    def __repr__(self):
        return f"<Node {self.node_type}:{self.id[:8]} '{self.content[:40]}...'>"


# ---- Edge ----

class Edge:
    """Связь между узлами графа."""

    def __init__(
        self,
        source_id: str,
        target_id: str,
        edge_type: str = "semantic",
        weight: float = 0.5,
        bidirectional: bool = False,
        metadata: Optional[dict] = None,
        edge_id: Optional[str] = None,
    ):
        if edge_type not in EDGE_TYPES:
            raise ValueError(f"Неизвестный тип связи: {edge_type}. Допустимые: {EDGE_TYPES}")

        self.id: str = edge_id or str(uuid.uuid4())
        self.source_id: str = source_id
        self.target_id: str = target_id
        self.edge_type: str = edge_type
        self.weight: float = max(0.0, min(1.0, weight))
        self.bidirectional: bool = bidirectional
        self.metadata: dict = metadata or {}
        self.created_at: str = datetime.utcnow().isoformat()
        self.updated_at: str = self.created_at
        self.evidence_count: int = 1  # сколько раз связь подтверждена

    def strengthen(self, delta: float = 0.1):
        """Усилить связь."""
        self.weight = min(1.0, self.weight + delta)
        self.evidence_count += 1
        self.updated_at = datetime.utcnow().isoformat()

    def weaken(self, delta: float = 0.1):
        """Ослабить связь."""
        self.weight = max(0.0, self.weight - delta)
        self.updated_at = datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type,
            "weight": self.weight,
            "bidirectional": self.bidirectional,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "evidence_count": self.evidence_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Edge":
        e = cls(
            source_id=data["source_id"],
            target_id=data["target_id"],
            edge_type=data.get("edge_type", "semantic"),
            weight=data.get("weight", 0.5),
            bidirectional=data.get("bidirectional", False),
            metadata=data.get("metadata"),
            edge_id=data.get("id"),
        )
        e.evidence_count = data.get("evidence_count", 1)
        e.created_at = data.get("created_at", e.created_at)
        e.updated_at = data.get("updated_at", e.updated_at)
        return e

    def __repr__(self):
        return f"<Edge {self.edge_type}:{self.source_id[:8]}→{self.target_id[:8]} w={self.weight:.2f}>"


# ---- Тесты ----

if __name__ == "__main__":
    print("=== Тест Node ===")
    n1 = Node(content="User installed Ubuntu 24.04", node_type="action", importance=0.8)
    n1.set_context("temporal", "2026-06")
    n1.set_context("spatial", "MacBook Pro 2012")
    n1.set_context("semantic", "системное администрирование")
    n1.touch()
    print(f"Создан: {n1}")
    print(f"Контекст: {n1.context}")
    print(f"Dict: {json.dumps(n1.to_dict(), ensure_ascii=False, indent=2)[:300]}...")

    print("\n=== Тест Edge ===")
    n2 = Node(content="Ubuntu 24.04 LTS", node_type="entity")
    e1 = Edge(n1.id, n2.id, edge_type="semantic", weight=0.9)
    print(f"Создана: {e1}")
    e1.strengthen()
    print(f"После strengthen: weight={e1.weight}, evidence={e1.evidence_count}")

    print("\n=== Тест from_dict ===")
    n3 = Node.from_dict(n1.to_dict())
    print(f"Восстановлен: {n3}")
    assert n3.id == n1.id
    assert n3.content == n1.content
    print("OK — roundtrip работает")

    print("\n=== Все тесты пройдены ===")
