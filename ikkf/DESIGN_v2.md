# I Know Kung Fu — Детальное проектирование

> Создано: 2026-06-08
> Версия: 2.0
> Основа: IMPLEMENTATION_PLAN.md v1.0 + результаты аудита 2026-06-08

---

## Фаза 0: Подготовка (1-2 дня)

### Шаг 0.1: Очистка диска

**Текущее состояние:** 98% (754MB free из 38GB)

**Что чистить (приоритет):**
```
/root/.cache/pip/          ~3.0 GB   — pip cache, можно удалить полностью
/root/.wp-cli/cache/       ~1.5 GB   — WP CLI темы/плагины
/root/awg0.conf.backup     ~4 KB     — старый бэкап VPN
/root/amnezia-clients-all.tar.gz — 50 KB, можно оставить
```

**Команды:**
```bash
rm -rf /root/.cache/pip
rm -rf /root/.wp-cli/cache
rm -f /root/awg0.conf.backup
```

**Ожидаемый результат:** +4.5GB свободного места (~90% → ~85%)

**Риск:** Низкий. pip cache пересоздаётся при установке. WP CLI кэш не нужен.

### Шаг 0.2: Резервное копирование IKKF

```bash
systemctl stop ikkf-api
cp -r /root/projects/i-know-kung-fu/data /root/projects/i-know-kung-fu/data-backup-2026-06-08
cp -r /root/projects/i-know-kung-fu/*.py /root/projects/i-know-kung-fu/code-backup/
systemctl start ikkf-api
curl http://127.0.0.1:8765/health → {"status":"ok"}
```

### Шаг 0.3: Проверка текущих компонентов

**Что уже есть (с прошлых сессий):**
- `/root/projects/i-know-kung-fu/graph/api.py` — заготовка FastAPI (заглушки)
- `/root/projects/i-know-kung-fu/graph/benchmark.py` — заготовка бенчмарков
- `/root/projects/i-know-kung-fu/graph/graph_rag.py` — заготовка RAG
- `/root/projects/i-know-kung-fu/graph/migrate_to_graph.py` — заготовка миграции
- `/root/projects/i-know-kung-fu/graph/schema/` — node.json, edge.json + документация
- `/root/projects/i-know-kung-fu/graph/IMPLEMENTATION_PLAN.md` — план v1.0

**Что НЕТ и нужно реализовать:**
- `node.py` — класс Node
- `edge.py` — класс Edge
- `graph.py` — KnowledgeGraph
- `storage.py` — SQLite backend
- `search.py` — поиск по графу
- `context.py` — ContextEncoder
- `predictive.py` — PredictiveCache
- `consolidation.py` — Consolidator

---

## Фаза 1: Граф знаний — Ядро (3-5 дней)

### Шаг 1.1: Node (узел графа)

**Файл:** `graph/node.py`

**Структура:**
```python
import uuid
from datetime import datetime

class Node:
    def __init__(self, content: str, node_type: str = 'fact',
                 embedding: list = None, context: dict = None,
                 tags: list = None, source: str = None):
        self.id = str(uuid.uuid4())
        self.content = content
        self.node_type = node_type  # fact/concept/event/skill/project/person/idea
        self.embedding = embedding or []
        self.context = context or {
            'temporal': None,    # когда создан/актуален
            'spatial': None,     # где (IP, город, "дома")
            'semantic': None,    # категория по смыслу
            'emotional': None,   # sentiment: positive/negative/neutral
            'social': None,      # упоминания людей/организаций
        }
        self.metadata = {
            'source': source or 'manual',
            'created': datetime.utcnow().isoformat(),
            'updated': datetime.utcnow().isoformat(),
            'version': 1,
        }
        self.importance = 0.5
        self.access_count = 0
        self.last_accessed = None
        self.tags = tags or []
        self.status = 'active'

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> 'Node':
        n = cls(content='', node_type='fact')
        n.__dict__.update(d)
        return n

    def touch(self):
        self.access_count += 1
        self.last_accessed = datetime.utcnow().isoformat()

    def update_importance(self, delta: float):
        self.importance = max(0.0, min(1.0, self.importance + delta))
        self.metadata['updated'] = datetime.utcnow().isoformat()
```

**Проверка:**
```bash
python3 -c "from graph.node import Node; n = Node(content='test', node_type='fact'); print(n.id, n.node_type, n.importance)"
```

### Шаг 1.2: Edge (связь)

**Файл:** `graph/edge.py`

```python
import uuid
from datetime import datetime

# 8 типов связей
EDGE_TYPES = [
    'semantic',      # семантическая (похожесть по смыслу)
    'temporal',      # временная (A произошло до B)
    'causal',        # причинно-следственная (A вызвало B)
    'associative',   # ассоциативная (A рядом с B)
    'hierarchical',  # иерархическая (A часть B)
    'contextual',    # контекстуальная (A и B в одном контексте)
    'similarity',    # по эмбеддингам (cosine > threshold)
    'sequence',      # последовательность (A → B в диалоге)
]

class Edge:
    def __init__(self, source_id: str, target_id: str,
                 edge_type: str = 'semantic', weight: float = 0.5,
                 bidirectional: bool = False):
        self.id = str(uuid.uuid4())
        self.source_id = source_id
        self.target_id = target_id
        self.edge_type = edge_type
        self.weight = weight
        self.bidirectional = bidirectional
        self.metadata = {
            'created': datetime.utcnow().isoformat(),
            'updated': datetime.utcnow().isoformat(),
            'evidence_count': 1,
        }

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> 'Edge':
        e = cls(source_id='', target_id='')
        e.__dict__.update(d)
        return e

    def strengthen(self, delta: float = 0.1):
        self.weight = min(1.0, self.weight + delta)
        self.metadata['evidence_count'] += 1
        self.metadata['updated'] = datetime.utcnow().isoformat()

    def weaken(self, delta: float = 0.1):
        self.weight = max(0.0, self.weight - delta)
        self.metadata['updated'] = datetime.utcnow().isoformat()
```

### Шаг 1.3: Storage (SQLite backend)

**Файл:** `graph/storage.py`

```python
import sqlite3
import json
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    embedding BLOB,
    node_type TEXT DEFAULT 'fact',
    context JSON,
    metadata JSON,
    importance REAL DEFAULT 0.5,
    access_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMP,
    tags JSON,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS edges (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    weight REAL DEFAULT 0.5,
    metadata JSON,
    bidirectional BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES nodes(id) ON DELETE CASCADE,
    FOREIGN KEY (target_id) REFERENCES nodes(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_nodes_status ON nodes(status);
CREATE INDEX IF NOT EXISTS idx_nodes_importance ON nodes(importance DESC);
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(edge_type);

CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
    content, tags,
    content='nodes',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS nodes_ai AFTER INSERT ON nodes BEGIN
    INSERT INTO nodes_fts(rowid, content, tags) VALUES (new.rowid, new.content, JSON_EXTRACT(new.tags, '$'));
END;

CREATE TRIGGER IF NOT EXISTS nodes_ad AFTER DELETE ON nodes BEGIN
    INSERT INTO nodes_fts(nodes_fts, rowid, content, tags) VALUES('delete', old.rowid, old.content, JSON_EXTRACT(old.tags, '$'));
END;

CREATE TRIGGER IF NOT EXISTS nodes_au AFTER UPDATE ON nodes BEGIN
    INSERT INTO nodes_fts(nodes_fts, rowid, content, tags) VALUES('delete', old.rowid, old.content, JSON_EXTRACT(old.tags, '$'));
    INSERT INTO nodes_fts(rowid, content, tags) VALUES (new.rowid, new.content, JSON_EXTRACT(new.tags, '$'));
END;
"""

class Storage:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)

    def save_node(self, node: dict) -> None:
        self.conn.execute("""
            INSERT OR REPLACE INTO nodes
            (id, content, embedding, node_type, context, metadata,
             importance, access_count, last_accessed, tags, status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            node['id'], node['content'],
            json.dumps(node.get('embedding', [])),
            node.get('node_type', 'fact'),
            json.dumps(node.get('context', {})),
            json.dumps(node.get('metadata', {})),
            node.get('importance', 0.5),
            node.get('access_count', 0),
            node.get('last_accessed'),
            json.dumps(node.get('tags', [])),
            node.get('status', 'active'),
        ))
        self.conn.commit()

    def get_node(self, node_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
        if not row:
            return None
        return self._row_to_node(row)

    def search_fts(self, query: str, limit: int = 10) -> list[dict]:
        """Полнотекстовый поиск через FTS5"""
        rows = self.conn.execute("""
            SELECT n.*, rank FROM nodes_fts fts
            JOIN nodes n ON n.rowid = nodes_fts.rowid
            WHERE nodes_fts MATCH ? AND n.status='active'
            ORDER BY rank LIMIT ?
        """, (query, limit)).fetchall()
        return [self._row_to_node(r) for r in rows]

    def get_neighbors(self, node_id: str, direction: str = 'both',
                      edge_type: str = None) -> list[dict]:
        """Получить соседей узла"""
        if direction == 'out':
            q = "SELECT n.* FROM edges e JOIN nodes n ON n.id = e.target_id WHERE e.source_id=?"
            params = [node_id]
        elif direction == 'in':
            q = "SELECT n.* FROM edges e JOIN nodes n ON n.id = e.source_id WHERE e.target_id=?"
            params = [node_id]
        else:
            q = """SELECT n.* FROM edges e JOIN nodes n ON
                    (n.id = e.target_id OR n.id = e.source_id)
                    WHERE (e.source_id=? OR e.target_id=?) AND n.id != ?"""
            params = [node_id, node_id, node_id]
        if edge_type:
            q += " AND e.edge_type=?"
            params.append(edge_type)
        rows = self.conn.execute(q, params).fetchall()
        return [self._row_to_node(r) for r in rows]

    def save_edge(self, edge: dict) -> None:
        self.conn.execute("""
            INSERT OR REPLACE INTO edges
            (id, source_id, target_id, edge_type, weight, metadata, bidirectional)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            edge['id'], edge['source_id'], edge['target_id'],
            edge['edge_type'], edge.get('weight', 0.5),
            json.dumps(edge.get('metadata', {})),
            edge.get('bidirectional', False),
        ))
        self.conn.commit()

    def count_nodes(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM nodes WHERE status='active'").fetchone()[0]

    def count_edges(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

    def _row_to_node(self, row) -> dict:
        return {
            'id': row[0], 'content': row[1],
            'embedding': json.loads(row[2]) if row[2] else [],
            'node_type': row[3], 'context': json.loads(row[4]) if row[4] else {},
            'metadata': json.loads(row[5]) if row[5] else {},
            'importance': row[6], 'access_count': row[7],
            'last_accessed': row[8],
            'tags': json.loads(row[9]) if row[9] else [],
            'status': row[10], 'created_at': row[11], 'updated_at': row[12],
        }
```

### Шаг 1.4: KnowledgeGraph (основной класс)

**Файл:** `graph/graph.py`

```python
from graph.node import Node
from graph.edge import Edge, EDGE_TYPES
from graph.storage import Storage
from collections import deque
import heapq

class KnowledgeGraph:
    def __init__(self, db_path: str, max_memory_nodes: int = 10000):
        self.storage = Storage(db_path)
        self.max_memory = max_memory_nodes
        self._cache = {}  # node_id -> Node (LRU)
        self._access_order = deque()

    # ── CRUD ──────────────────────────────────────────────────────

    def add_node(self, content: str, node_type: str = 'fact',
                 embedding: list = None, context: dict = None,
                 tags: list = None, source: str = None) -> Node:
        node = Node(content=content, node_type=node_type,
                    embedding=embedding, context=context,
                    tags=tags, source=source)
        self.storage.save_node(node.to_dict())
        self._cache_node(node)
        return node

    def get_node(self, node_id: str) -> Node | None:
        if node_id in self._cache:
            self._cache[node_id].touch()
            return self._cache[node_id]
        data = self.storage.get_node(node_id)
        if data:
            node = Node.from_dict(data)
            self._cache_node(node)
            return node
        return None

    def update_node(self, node_id: str, **kwargs) -> Node | None:
        node = self.get_node(node_id)
        if not node:
            return None
        for k, v in kwargs.items():
            if hasattr(node, k):
                setattr(node, k, v)
        node.metadata['updated'] = __import__('datetime').datetime.utcnow().isoformat()
        node.metadata['version'] = node.metadata.get('version', 1) + 1
        self.storage.save_node(node.to_dict())
        return node

    def delete_node(self, node_id: str) -> bool:
        self._cache.pop(node_id, None)
        # SQLite ON DELETE CASCADE удалит связанные edges
        self.storage.conn.execute("DELETE FROM nodes WHERE id=?", (node_id,))
        self.storage.conn.commit()
        return True

    # ── Связи ──────────────────────────────────────────────────────

    def add_edge(self, source_id: str, target_id: str,
                 edge_type: str = 'semantic', weight: float = 0.5,
                 bidirectional: bool = False) -> Edge:
        edge = Edge(source_id=source_id, target_id=target_id,
                    edge_type=edge_type, weight=weight,
                    bidirectional=bidirectional)
        self.storage.save_edge(edge.to_dict())
        return edge

    def get_neighbors(self, node_id: str, depth: int = 1) -> list[Node]:
        visited = {node_id}
        current_level = [node_id]
        result = []
        for _ in range(depth):
            next_level = []
            for nid in current_level:
                neighbor_data = self.storage.get_neighbors(nid)
                for nd in neighbor_data:
                    if nd['id'] not in visited:
                        visited.add(nd['id'])
                        result.append(Node.from_dict(nd))
                        next_level.append(nd['id'])
            current_level = next_level
        return result

    def find_path(self, source_id: str, target_id: str,
                  max_depth: int = 6) -> list[str]:
        """BFS поиск пути между узлами"""
        if source_id == target_id:
            return [source_id]
        visited = {source_id}
        queue = deque([(source_id, [source_id])])
        while queue:
            current, path = queue.popleft()
            if len(path) > max_depth:
                return []
            neighbors = self.storage.get_neighbors(current)
            for n in neighbors:
                nid = n['id']
                if nid == target_id:
                    return path + [nid]
                if nid not in visited:
                    visited.add(nid)
                    queue.append((nid, path + [nid]))
        return []

    # ── Поиск ──────────────────────────────────────────────────────

    def search(self, query: str, mode: str = 'hybrid',
               limit: int = 10) -> list[tuple[Node, float]]:
        """
        Режимы:
        - fts: полнотекстовый через FTS5
        - vector: поиск по эмбеддингам (если есть)
        - hybrid: комбинация FTS + vector
        """
        if mode in ('fts', 'hybrid'):
            results = self.storage.search_fts(query, limit=limit)
            return [(Node.from_dict(r), 0.5) for r in results[:limit]]
        return []

    # ── Статистика ─────────────────────────────────────────────────

    def stats(self) -> dict:
        return {
            'nodes': self.storage.count_nodes(),
            'edges': self.storage.count_edges(),
            'cache_size': len(self._cache),
            'cache_capacity': self.max_memory,
        }

    # ── Внутренние методы ─────────────────────────────────────────

    def _cache_node(self, node: Node):
        if len(self._cache) >= self.max_memory:
            if self._access_order:
                evict_id = self._access_order.popleft()
                self._cache.pop(evict_id, None)
        self._cache[node.id] = node
        self._access_order.append(node.id)
```

### Шаг 1.5: ContextEncoder (контекстное кодирование)

**Файл:** `graph/context.py`

```python
import re
from datetime import datetime

class ContextEncoder:
    """
    5 измерений контекста:
    temporal  — даты, время, "вчера", "завтра"
    spatial   — города, страны, IP, "дома"
    semantic  — категория по ключевым словам
    emotional — sentiment (positive/negative/neutral)
    social    — упоминания людей, организаций
    """

    # Простые эвристики для извлечения
    DATE_PATTERNS = [
        r'\d{4}-\d{2}-\d{2}',
        r'\d{2}\.\d{2}\.\d{4}',
        r'вчера|сегодня|завтра|позавчера',
    ]
    EMOTION_WORDS = {
        'positive': ['отлично', 'супер', 'класс', 'хорошо', 'прекрасно', 'успех', 'победа'],
        'negative': ['плохо', 'проблема', 'ошибка', 'баг', 'сломан', 'фрустрация', 'провал'],

    }

    def extract_from_text(self, text: str) -> dict:
        return {
            'temporal': self._extract_temporal(text),
            'spatial': self._extract_spatial(text),
            'semantic': self._extract_semantic(text),
            'emotional': self._extract_emotional(text),
            'social': self._extract_social(text),
        }

    def similarity(self, ctx1: dict, ctx2: dict) -> float:
        """Сходство двух контекстов (0.0-1.0)"""
        score = 0.0
        weights = {'temporal': 0.2, 'spatial': 0.2, 'semantic': 0.3, 'emotional': 0.15, 'social': 0.15}
        for dim, weight in weights.items():
            v1, v2 = ctx1.get(dim), ctx2.get(dim)
            if v1 and v2:
                if v1 == v2:
                    score += weight
                elif isinstance(v1, str) and isinstance(v2, str):
                    # Простое сравнение: пересечение слов
                    words1, words2 = set(v1.lower().split()), set(v2.lower().split())
                    if words1 & words2:
                        score += weight * len(words1 & words2) / max(len(words1 | words2), 1)
        return score

    def _extract_temporal(self, text: str) -> str | None:
        for pat in self.DATE_PATTERNS:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group()
        return None

    def _extract_spatial(self, text: str) -> str | None:
        cities = ['Москва', 'Питер', 'Санкт-Петербург', 'Новосибирск', 'Екатеринбург']
        text_lower = text.lower()
        for city in ['moscow', 'london', 'berlin', 'paris']:
            if city in text_lower:
                return city
        return None

    def _extract_semantic(self, text: str) -> str | None:
        categories = {
            'разработка': ['python', 'код', 'api', 'сервер', 'база', 'скрипт', 'функция'],
            'безопасность': ['ssh', 'firewall', 'пароль', 'доступ', 'уязвимость'],
            'devops': ['docker', 'nginx', 'systemd', 'cron', 'деплой'],
            'ai': ['ikkf', 'граф', 'нода', 'embedding', 'qwen', 'llm', 'rag'],
        }
        text_lower = text.lower()
        for cat, keywords in categories.items():
            if any(kw in text_lower for kw in keywords):
                return cat
        return None

    def _extract_emotional(self, text: str) -> str:
        text_lower = text.lower()
        for emotion, words in self.EMOTION_WORDS.items():
            if any(w in text_lower for w in words):
                return emotion
        return 'neutral'

    def _extract_social(self, text: str) -> list[str]:
        # Ищем @упоминания и имена
        mentions = re.findall(r'@(\w+)', text)
        names = re.findall(r'\b[А-Я][а-я]+\b', text)
        return list(set(mentions + names))
```

### Шаг 1.6: PredictiveCache (предиктивная подгрузка)

**Файл:** `graph/predictive.py`

```python
from collections import defaultdict
import heapq

class PredictiveCache:
    def __init__(self, graph, cache_size: int = 1000):
        self.graph = graph
        self.cache_size = cache_size
        self.transition_counts = defaultdict(lambda: defaultdict(int))
        self.total_transitions = defaultdict(int)

    def record_access(self, node_id: str):
        """Записать доступ к узлу для обучения модели"""
        # Обновляем transition counts в базе
        node = self.graph.get_node(node_id)
        if node:
            node.touch()
            self.graph.storage.save_node(node.to_dict())

    def record_transition(self, from_id: str, to_id: str):
        """Записать переход между узлами"""
        self.transition_counts[from_id][to_id] += 1
        self.total_transitions[from_id] += 1

    def predict_next(self, node_id: str, limit: int = 10) -> list[tuple[str, float]]:
        """Предсказать следующие узлы на основе истории переходов"""
        transitions = self.transition_counts.get(node_id, {})
        total = self.total_transitions.get(node_id, 1)
        probs = [(target, count/total) for target, count in transitions.items()]
        return heapq.nlargest(limit, probs, key=lambda x: x[1])

    def get_stats(self) -> dict:
        return {
            'unique_sources': len(self.transition_counts),
            'total_transitions': sum(self.total_transitions.values()),
            'cache_size': len(self.graph._cache),
            'cache_capacity': self.graph.max_memory,
        }
```

### Шаг 1.7: Consolidator (ночная консолидация)

**Файл:** `graph/consolidation.py`

```python
import numpy as np
from datetime import datetime, timedelta

class Consolidator:
    def __init__(self, graph):
        self.graph = graph
        self.duplicate_threshold = 0.95
        self.edge_discovery_threshold = 0.7

    def run_full_cycle(self) -> dict:
        """Полный цикл консолидации"""
        results = {
            'started': datetime.utcnow().isoformat(),
            'duplicates_found': 0,
            'nodes_merged': 0,
            'edges_discovered': 0,
            'nodes_archived': 0,
        }

        # 1. Найти и слить дубликаты
        duplicates = self.find_duplicates()
        for dup_group in duplicates:
            self.merge_nodes(dup_group)
            results['nodes_merged'] += len(dup_group) - 1
        results['duplicates_found'] = len(duplicates)

        # 2. Обнаружить новые связи
        new_edges = self.discover_edges()
        results['edges_discovered'] = new_edges

        # 3. Пересчитать важность (PageRank)
        self.calculate_importance()

        # 4. Архивировать старое
        archived = self.archive_old(days=90)
        results['nodes_archived'] = archived

        results['finished'] = datetime.utcnow().isoformat()
        return results

    def find_duplicates(self) -> list[list[str]]:
        """Найти дубликаты через cosine similarity эмбеддингов"""
        nodes = self.graph.storage.conn.execute(
            "SELECT id, embedding FROM nodes WHERE status='active' AND embedding IS NOT NULL"
        ).fetchall()
        duplicates = []
        seen = set()
        for i, (id1, emb1_json) in enumerate(nodes):
            if id1 in seen:
                continue
            emb1 = json.loads(emb1_json)
            group = [id1]
            for j, (id2, emb2_json) in enumerate(nodes):
                if i != j and id2 not in seen:
                    emb2 = json.loads(emb2_json)
                    sim = self._cosine_sim(emb1, emb2)
                    if sim > self.duplicate_threshold:
                        group.append(id2)
                        seen.add(id2)
            if len(group) > 1:
                duplicates.append(group)
                seen.add(id1)
        return duplicates

    def merge_nodes(self, node_ids: list[str]) -> str:
        """Объединить узлы в один, усилить связи"""
        if len(node_ids) < 2:
            return node_ids[0] if node_ids else None
        primary = self.graph.get_node(node_ids[0])
        for other_id in node_ids[1:]:
            other = self.graph.get_node(other_id)
            if other:
                primary.content += f" | {other.content}"
                primary.importance = max(primary.importance, other.importance)
                primary.access_count += other.access_count
                primary.tags = list(set(primary.tags + other.tags))
                self.graph.storage.conn.execute("UPDATE nodes SET status='merged' WHERE id=?", (other_id,))
        self.graph.storage.save_node(primary.to_dict())
        self.graph.storage.conn.commit()
        return primary.id

    def discover_edges(self) -> int:
        """Обнаружить новые связи между похожими узлами"""
        nodes = self.graph.storage.conn.execute(
            "SELECT id, embedding FROM nodes WHERE status='active' AND embedding IS NOT NULL"
        ).fetchall()
        count = 0
        for i, (id1, emb1_json) in enumerate(nodes):
            emb1 = json.loads(emb1_json)
            for j, (id2, emb2_json) in enumerate(nodes):
                if i < j:
                    emb2 = json.loads(emb2_json)
                    sim = self._cosine_sim(emb1, emb2)
                    if sim > self.edge_discovery_threshold:
                        self.graph.add_edge(id1, id2, 'similarity', weight=sim)
                        count += 1
        return count

    def calculate_importance(self, iterations: int = 10):
        """PageRank-подобный расчёт важности"""
        nodes = self.graph.storage.conn.execute(
            "SELECT id FROM nodes WHERE status='active'"
        ).fetchall()
        ids = [n[0] for n in nodes]
        importance = {nid: 0.5 for nid in ids}

        for _ in range(iterations):
            new_imp = {}
            for nid in ids:
                neighbors = self.graph.storage.get_neighbors(nid)
                score = 0.1
                for n in neighbors:
                    edges = self.graph.storage.conn.execute(
                        "SELECT weight FROM edges WHERE source_id=? AND target_id=?",
                        (n['id'], nid)
                    ).fetchall()
                    for e in edges:
                        score += 0.9 * e[0] * importance.get(n['id'], 0.5)
                new_imp[nid] = min(1.0, score)
            importance = new_imp

        for nid, imp in importance.items():
            self.graph.storage.conn.execute(
                "UPDATE nodes SET importance=? WHERE id=?", (imp, nid)
            )
        self.graph.storage.conn.commit()

    def archive_old(self, days: int = 90) -> int:
        """Архивировать узлы без доступа старше N дней"""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        result = self.graph.storage.conn.execute("""
            UPDATE nodes SET status='archived'
            WHERE status='active'
            AND (last_accessed IS NULL OR last_accessed < ?)
            AND created_at < ?
        """, (cutoff, cutoff))
        self.graph.storage.conn.commit()
        return result.rowcount

    @staticmethod
    def _cosine_sim(a: list, b: list) -> float:
        if not a or not b:
            return 0.0
        a, b = np.array(a), np.array(b)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
```

---

## Фаза 2: API и интеграция (2-3 дня)

### Шаг 2.1: FastAPI endpoints (порт 8766)

**Файл:** `graph/api.py` (переписать существующий)

```python
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from graph.graph import KnowledgeGraph
from graph.consolidator import Consolidator

app = FastAPI(title="IKKF Graph API", version="2.0")

# Глобальный граф
graph = KnowledgeGraph(db_path="/root/projects/i-know-kung-fu/data/graph.db")

# ── Models ──────────────────────────────────────────────────────

class NodeCreate(BaseModel):
    content: str
    node_type: str = "fact"
    context: Optional[dict] = None
    tags: Optional[List[str]] = None
    source: Optional[str] = None

class NodeUpdate(BaseModel):
    content: Optional[str] = None
    context: Optional[dict] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = None

class EdgeCreate(BaseModel):
    source_id: str
    target_id: str
    edge_type: str = "semantic"
    weight: float = 0.5
    bidirectional: bool = False

class SearchQuery(BaseModel):
    query: str
    mode: str = "hybrid"  # fts / vector / hybrid
    limit: int = 10
    project: Optional[str] = None

# ── Health ──────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0"}

@app.get("/stats")
def stats():
    return graph.stats()

# ── Nodes ──────────────────────────────────────────────────────

@app.post("/nodes")
def create_node(data: NodeCreate):
    node = graph.add_node(
        content=data.content,
        node_type=data.node_type,
        context=data.context,
        tags=data.tags,
        source=data.source,
    )
    return {"id": node.id, "content": node.content}

@app.get("/nodes/{node_id}")
def get_node(node_id: str):
    node = graph.get_node(node_id)
    if not node:
        raise HTTPException(404, "Node not found")
    return node.to_dict()

@app.put("/nodes/{node_id}")
def update_node(node_id: str, data: NodeUpdate):
    updates = {k: v for k, v in data.dict().items() if v is not None}
    node = graph.update_node(node_id, **updates)
    if not node:
        raise HTTPException(404, "Node not found")
    return node.to_dict()

@app.delete("/nodes/{node_id}")
def delete_node(node_id: str):
    graph.delete_node(node_id)
    return {"deleted": True}

@app.get("/nodes")
def list_nodes(
    node_type: Optional[str] = None,
    status: str = "active",
    limit: int = 50,
    offset: int = 0,
):
    # TODO: реализовать через storage
    return {"nodes": [], "limit": limit, "offset": offset}

# ── Edges ──────────────────────────────────────────────────────

@app.post("/edges")
def create_edge(data: EdgeCreate):
    edge = graph.add_edge(
        source_id=data.source_id,
        target_id=data.target_id,
        edge_type=data.edge_type,
        weight=data.weight,
        bidirectional=data.bidirectional,
    )
    return {"id": edge.id}

@app.get("/neighbors/{node_id}")
def get_neighbors(node_id: str, depth: int = 1, edge_type: Optional[str] = None):
    neighbors = graph.get_neighbors(node_id, depth=depth)
    return {"neighbors": [n.to_dict() for n in neighbors]}

@app.get("/path/{source_id}/{target_id}")
def find_path(source_id: str, target_id: str, max_depth: int = 6):
    path = graph.find_path(source_id, target_id, max_depth=max_depth)
    return {"path": path, "length": len(path)}

# ── Search ─────────────────────────────────────────────────────

@app.post("/search")
def search(data: SearchQuery):
    results = graph.search(data.query, mode=data.mode, limit=data.limit)
    return {
        "query": data.query,
        "results": [{"id": n.id, "content": n.content[:200], "score": s} for n, s in results],
        "count": len(results),
    }

# ── Consolidation ──────────────────────────────────────────────

@app.post("/consolidate")
def consolidate():
    c = Consolidator(graph)
    results = c.run_full_cycle()
    return results

@app.post("/migrate")
def migrate():
    """Миграция из ChromaDB в граф"""
    # TODO: реализовать
    return {"status": "not implemented"}
```

### Шаг 2.2: Миграция из ChromaDB

**Файл:** `graph/migrate.py` (переписать существующий)

```python
import sys
sys.path.insert(0, '/root/projects/i-know-kung-fu')
from graph.graph import KnowledgeGraph
from graph.context import ContextEncoder

def migrate_from_chroma(chroma_path: str, graph: KnowledgeGraph) -> dict:
    """Мигрировать все документы из ChromaDB в граф"""
    try:
        import chromadb
        client = chromadb.PersistentClient(path=chroma_path)
        collection = client.get_or_create_collection("ikkf")
        
        all_data = collection.get(include=["documents", "embeddings", "metadatas"])
        
        migrated = 0
        errors = 0
        
        for i, doc in enumerate(all_data["documents"]):
            try:
                embedding = all_data["embeddings"][i] if all_data["embeddings"] else []
                metadata = all_data["metadatas"][i] if all_data["metadatas"] else {}
                
                # Извлечь контекст из текста
                ctx = ContextEncoder().extract_from_text(doc)
                
                node = graph.add_node(
                    content=doc,
                    node_type=metadata.get("type", "fact"),
                    embedding=embedding,
                    context=ctx,
                    tags=metadata.get("tags", []),
                    source=metadata.get("source", "chroma_migration"),
                )
                migrated += 1
            except Exception as e:
                errors += 1
                print(f"Error migrating doc {i}: {e}")
        
        # Создать связи между похожими мигрированными узлами
        # (можно запустить отдельно через Consolidator.discover_edges)
        
        return {"migrated": migrated, "errors": errors}
    except ImportError:
        return {"error": "chromadb not installed"}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    g = KnowledgeGraph("/root/projects/i-know-kung-fu/data/graph.db")
    result = migrate_from_chroma("/root/projects/i-know-kung-fu/data/vectors", g)
    print(result)
```

### Шаг 2.3: Интеграция с существующим IKKF

**Что нужно обновить:**
1. `kungfu_skill.py` — поиск через Graph вместо ChromaDB
2. `auto_save.py` — сохранение в Graph
3. `kungfu_llm.py` — RAG через Graph

**Обновление kungfu_skill.py:**
```python
# Добавить в конец файла:
def search_graph(query: str, top_k: int = 5) -> str:
    """Поиск через граф (fallback для ChromaDB)"""
    try:
        from graph.graph import KnowledgeGraph
        g = KnowledgeGraph("/root/projects/i-know-kung-fu/data/graph.db")
        results = g.search(query, mode='hybrid', limit=top_k)
        if results:
            parts = []
            for node, score in results:
                parts.append(f"[score: {score:.2f}] {node.content}")
            return "\n\n".join(parts)
    except Exception:
        pass
    return ""
```

---

## Фаза 3: RAG через граф (2-3 дня)

### Шаг 3.1: GraphRAG

**Файл:** `graph/graph_rag.py` (переписать существующий)

```python
from graph.graph import KnowledgeGraph
from graph.context import ContextEncoder

class GraphRAG:
    def __init__(self, graph: KnowledgeGraph, llm=None):
        self.graph = graph
        self.llm = llm  # QwenLLM или внешний
        self.context_encoder = ContextEncoder()

    def query(self, question: str, context_depth: int = 2) -> str:
        """
        Полный RAG-цикл:
        1. Извлечь ключевые слова
        2. Найти стартовые узлы
        3. Расширить граф (BFS)
        4. Ранжировать
        5. Сформировать контекст
        6. Отправить в LLM
        7. Сохранить Q&A
        """
        # 1. Поиск стартовых узлов
        results = self.graph.search(question, mode='hybrid', limit=5)
        if not results:
            return "Ничего не найдено в базе знаний."

        seed_nodes = [n for n, s in results]

        # 2. Расширить граф
        all_nodes = set()
        for node in seed_nodes:
            all_nodes.add(node.id)
            neighbors = self.graph.get_neighbors(node.id, depth=context_depth)
            for n in neighbors:
                all_nodes.add(n.id)

        # 3. Ранжировать по важности и сходству
        ranked = []
        for nid in all_nodes:
            n = self.graph.get_node(nid)
            if n:
                # Простое ранжирование: importance + access_count
                score = n.importance + min(n.access_count * 0.01, 0.3)
                ranked.append((n, score))

        ranked.sort(key=lambda x: x[1], reverse=True)
        top_nodes = ranked[:10]

        # 4. Сформировать контекст
        context_parts = []
        for node, score in top_nodes:
            context_parts.append(f"[{node.node_type}] {node.content}")

        context = "\n\n".join(context_parts)

        # 5. Ответ (без LLM — просто вернуть контекст)
        if self.llm:
            prompt = f"Используя контекст ниже, ответь на вопрос.\n\nКОНТЕКСТ:\n{context}\n\nВОПРОС: {question}\n\nОТВЕТ:"
            answer = self.llm.generate(prompt)
        else:
            answer = f"Контекст для вопроса '{question}':\n\n{context}"

        # 6. Сохранить Q&A как новые узлы
        self.graph.add_node(
            content=f"Q: {question}\nA: {answer}",
            node_type="qa",
            source="graph_rag",
        )

        return answer
```

---

## Фаза 4: Тестирование (1-2 дня)

### Шаг 4.1: Unit-тесты

**Структура:**
```
tests/
├── test_node.py
├── test_edge.py
├── test_graph.py
├── test_storage.py
├── test_context.py
├── test_predictive.py
├── test_consolidation.py
└── test_api.py
```

**Пример test_node.py:**
```python
import pytest
from graph.node import Node

def test_node_creation():
    n = Node(content="test fact", node_type="fact")
    assert n.id is not None
    assert n.content == "test fact"
    assert n.node_type == "fact"
    assert n.importance == 0.5
    assert n.status == "active"

def test_node_serialization():
    n = Node(content="test", tags=["tag1"])
    d = n.to_dict()
    n2 = Node.from_dict(d)
    assert n2.content == "test"
    assert n2.tags == ["tag1"]

def test_node_touch():
    n = Node(content="test")
    assert n.access_count == 0
    n.touch()
    assert n.access_count == 1
    assert n.last_accessed is not None
```

### Шаг 4.2: Бенчмарки

**Файл:** `graph/benchmark.py` (переписать существующий)

```python
import time
import random
from graph.graph import KnowledgeGraph

def benchmark_search(n_nodes: int = 1000):
    """Бенчмарк поиска"""
    g = KnowledgeGraph(":memory:")

    # Генерируем тестовые данные
    print(f"Создание {n_nodes} узлов...")
    for i in range(n_nodes):
        g.add_node(
            content=f"Test document number {i} with some content about topic {i % 10}",
            node_type=random.choice(["fact", "concept", "event"]),
            tags=[f"tag_{i % 5}"],
        )

    # Бенчмарк FTS поиска
    queries = ["Test", "document", "topic", "number", "content"]
    times = []
    for q in queries:
        start = time.time()
        results = g.search(q, mode='fts', limit=10)
        elapsed = time.time() - start
        times.append(elapsed)
        print(f"  FTS '{q}': {elapsed:.4f}s, {len(results)} results")

    print(f"\nСреднее время FTS: {sum(times)/len(times):.4f}s")
    print(f"Статистика: {g.stats()}")

if __name__ == "__main__":
    benchmark_search(1000)
```

---

## Фаза 5: Развёртывание (1 день)

### Шаг 5.1: systemd unit

```ini
# /etc/systemd/system/ikkf-graph.service
[Unit]
Description=IKKF Graph API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/projects/i-know-kung-fu
ExecStart=/usr/local/lib/hermes-agent/venv/bin/python3 -m uvicorn graph.api:app --host 127.0.0.1 --port 8766
Restart=always
RestartSec=5
StandardOutput=append:/var/log/ikkf-graph.log
StandardError=append:/var/log/ikkf-graph.log

[Install]
WantedBy=multi-user.target
```

### Шаг 5.2: Cron для консолидации

```bash
# Каждую ночь в 3:00 UTC
0 3 * * * cd /root/projects/i-know-kung-fu && /usr/local/lib/hermes-agent/venv/bin/python3 -c "from graph.consolidation import Consolidator; from graph.graph import KnowledgeGraph; g = KnowledgeGraph('data/graph.db'); c = Consolidator(g); c.run_full_cycle()" >> /var/log/ikkf-consolidation.log 2>&1
```

---

## Фаза 6-8: Документация, OWL Robot, AI Affiliate Engine

(Детализируются после завершения Фаз 1-5)

---

## Зависимости

```bash
# requirements.txt для graph/
fastapi>=0.100
uvicorn>=0.23
numpy>=1.24
pytest>=7.0
```

## Порты

| Сервис | Порт | Назначение |
|--------|------|------------|
| IKKF API (старый) | 8765 | ChromaDB + FTS5 (оставить как fallback) |
| Graph API (новый) | 8766 | Граф знаний |

## Файловая структура (итоговая)

```
/root/projects/i-know-kung-fu/
├── graph/
│   ├── __init__.py
│   ├── node.py           ← НОВЫЙ
│   ├── edge.py           ← НОВЫЙ
│   ├── graph.py          ← НОВЫЙ (KnowledgeGraph)
│   ├── storage.py        ← НОВЫЙ (SQLite backend)
│   ├── search.py         ← НОВЫЙ (BFS/DFS/vector)
│   ├── context.py        ← НОВЫЙ (ContextEncoder)
│   ├── predictive.py     ← НОВЫЙ (PredictiveCache)
│   ├── consolidation.py  ← НОВЫЙ (Consolidator)
│   ├── api.py            ← ПЕРЕПИСАТЬ (FastAPI)
│   ├── migrate.py        ← ПЕРЕПИСАТЬ (ChromaDB → Graph)
│   ├── benchmark.py      ← ПЕРЕПИСАТЬ
│   ├── graph_rag.py      ← ПЕРЕПИСАТЬ
│   ├── schema/
│   │   ├── node.json
│   │   ├── edge.json
│   │   ├── context-encoding.md
│   │   ├── predictive-preload.md
│   │   ├── storage-hierarchy.md
│   │   └── consolidation.md
│   └── IMPLEMENTATION_PLAN.md
├── tests/
│   ├── test_node.py
│   ├── test_edge.py
│   ├── test_graph.py
│   ├── test_storage.py
│   ├── test_context.py
│   ├── test_predictive.py
│   ├── test_consolidation.py
│   └── test_api.py
└── data/
    ├── graph.db           ← НОВАЯ SQLite БД
    ├── vectors/           ← ChromaDB (оставить)
    └── index/             ← FTS5 (оставить)
```
