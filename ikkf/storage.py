"""
IKKF — Storage (SQLite backend)

Иерархия хранения:
- L1: RAM (in-memory dict, быстрый доступ к горячим узлам)
- L2: SQLite на SSD (персистентное хранение)
- L3: архив (редко используемые узлы, можно выгрузить)

Схема БД:
- nodes: все узлы
- edges: все связи
- node_tags: теги узлов (для быстрого поиска)
- access_log: лог доступов (для анализа популярности)
"""

import sqlite3
import json
import os
import numpy as np
from datetime import datetime
from typing import Optional

from .node import Node, Edge


def _decode_embedding(data):
    """Decode embedding from bytes (numpy) or JSON string."""
    if data is None:
        return None
    if isinstance(data, bytes):
        return np.frombuffer(data, dtype=np.float32).tolist()
    if isinstance(data, str):
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return None
    if isinstance(data, list):
        return data
    return None


# ---- DDL ----

NODES_TABLE = """
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    node_type TEXT NOT NULL DEFAULT 'fact',
    embedding BLOB,
    context TEXT DEFAULT '{}',
    metadata TEXT DEFAULT '{}',
    importance REAL DEFAULT 0.5,
    tags TEXT DEFAULT '[]',
    source TEXT DEFAULT 'api',
    project TEXT DEFAULT 'default',
    access_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_accessed TEXT,
    history TEXT DEFAULT '[]'
);
"""

EDGES_TABLE = """
CREATE TABLE IF NOT EXISTS edges (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    edge_type TEXT NOT NULL DEFAULT 'semantic',
    weight REAL DEFAULT 0.5,
    bidirectional INTEGER DEFAULT 0,
    metadata TEXT DEFAULT '{}',
    evidence_count INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES nodes(id),
    FOREIGN KEY (target_id) REFERENCES nodes(id)
);
"""

# ---- Tables from old IKKF (для совместимости) ----

PROJECTS_TABLE = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
"""

DOCUMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    source TEXT NOT NULL,
    file_type TEXT,
    file_size INTEGER,
    content_hash TEXT,
    indexed_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (project_id) REFERENCES projects(id)
);
"""

CHUNKS_TABLE = """
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT,
    project_id TEXT,
    content TEXT NOT NULL,
    position INTEGER,
    char_count INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (document_id) REFERENCES documents(id),
    FOREIGN KEY (project_id) REFERENCES projects(id)
);
"""

FTS_TABLE = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    content, chunk_id UNINDEXED, document_id UNINDEXED, project_id UNINDEXED
);

CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
    content, node_id UNINDEXED, project UNINDEXED,
    tokenize='unicode61'
);

CREATE TRIGGER IF NOT EXISTS nodes_fts_ai AFTER INSERT ON nodes BEGIN
    INSERT INTO nodes_fts(rowid, content, node_id, project)
    VALUES (new.rowid, new.content, new.id, new.project);
END;

CREATE TRIGGER IF NOT EXISTS nodes_fts_au AFTER UPDATE ON nodes BEGIN
    DELETE FROM nodes_fts WHERE node_id = old.id;
    INSERT INTO nodes_fts(rowid, content, node_id, project)
    VALUES (new.rowid, new.content, new.id, new.project);
END;

CREATE TRIGGER IF NOT EXISTS chunks_fts_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, content, chunk_id, document_id, project_id)
    VALUES (new.rowid, new.content, new.id, new.document_id, new.project_id);
END;

CREATE TRIGGER IF NOT EXISTS chunks_fts_au AFTER UPDATE ON chunks BEGIN
    DELETE FROM chunks_fts WHERE chunk_id = old.id;
    INSERT INTO chunks_fts(rowid, content, chunk_id, document_id, project_id)
    VALUES (new.rowid, new.content, new.id, new.document_id, new.project_id);
END;
"""

# ---- Embeddings table for vector search ----

EMBEDDINGS_TABLE = """
CREATE TABLE IF NOT EXISTS node_embeddings (
    node_id TEXT PRIMARY KEY,
    embedding BLOB NOT NULL,
    dim INTEGER DEFAULT 384,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (node_id) REFERENCES nodes(id) ON DELETE CASCADE
);
"""

# sqlite-vec virtual table for HNSW-like approximate nearest neighbor search
# Falls back gracefully if sqlite-vec extension not available
SQLITE_VEC_TABLE = """
CREATE VIRTUAL TABLE IF NOT EXISTS node_embeddings_vec USING vec0(
    node_id TEXT PRIMARY KEY,
    embedding FLOAT[384] distance_metric=cosine
);
"""

# ---- Semantic Cache table ----

CACHE_TABLE = """
CREATE TABLE IF NOT EXISTS semantic_cache (
    query_hash TEXT PRIMARY KEY,
    query_text TEXT NOT NULL,
    response_text TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    hits INTEGER DEFAULT 0
);
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type);",
    "CREATE INDEX IF NOT EXISTS idx_nodes_project ON nodes(project);",
    "CREATE INDEX IF NOT EXISTS idx_nodes_status ON nodes(status);",
    "CREATE INDEX IF NOT EXISTS idx_nodes_importance ON nodes(importance DESC);",
    "CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);",
    "CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);",
    "CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(edge_type);",
    "CREATE INDEX IF NOT EXISTS idx_edges_weight ON edges(weight DESC);",
    "CREATE INDEX IF NOT EXISTS idx_chunks_project ON chunks(project_id);",
    "CREATE INDEX IF NOT EXISTS idx_chunks_created ON chunks(created_at);",
    "CREATE INDEX IF NOT EXISTS idx_documents_project ON documents(project_id);",
    "CREATE INDEX IF NOT EXISTS idx_node_embeddings_node ON node_embeddings(node_id);",
]


class Storage:
    """SQLite хранилище для графа знаний."""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), "..", "data", "graph.db")
        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA busy_timeout=5000;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.conn.execute("PRAGMA foreign_keys=ON;")
        self._init_schema()

    def _init_schema(self):
        """Создать таблицы и индексы."""
        self.conn.execute(NODES_TABLE)
        self.conn.execute(EDGES_TABLE)
        self.conn.execute(PROJECTS_TABLE)
        self.conn.execute(DOCUMENTS_TABLE)
        self.conn.execute(CHUNKS_TABLE)
        self.conn.execute(EMBEDDINGS_TABLE)
        self.conn.execute(CACHE_TABLE)
        self.conn.executescript(FTS_TABLE)
        for idx in INDEXES:
            self.conn.execute(idx)
        self.conn.commit()
        self._init_vec_table()
        self._migrate_fts_schema()

    def _migrate_fts_schema(self):
        """Миграция: пересоздать nodes_fts если старая схема (без node_id)."""
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT sql FROM sqlite_master WHERE name='nodes_fts'")
            row = cur.fetchone()
            if row and 'node_id' not in row[0]:
                # Старая схема — пересоздаём
                cur.execute("DROP TABLE IF EXISTS nodes_fts")
                cur.execute("DROP TRIGGER IF EXISTS nodes_fts_ai")
                cur.execute("DROP TRIGGER IF EXISTS nodes_fts_au")
                cur.execute("""
                    CREATE VIRTUAL TABLE nodes_fts USING fts5(
                        content, node_id UNINDEXED, project UNINDEXED,
                        tokenize='unicode61'
                    )
                """)
                cur.execute("""
                    INSERT INTO nodes_fts(rowid, content, node_id, project)
                    SELECT rowid, content, id, project FROM nodes WHERE status='active'
                """)
                cur.execute("""
                    CREATE TRIGGER nodes_fts_ai AFTER INSERT ON nodes BEGIN
                        INSERT INTO nodes_fts(rowid, content, node_id, project)
                        VALUES (new.rowid, new.content, new.id, new.project);
                    END
                """)
                # nodes_fts_au (UPDATE trigger) — не создаём.
                # UPDATE управляется вручную в save_node (DELETE + INSERT в FTS).
                # Триггер конфликтует с ручным управлением и вызывает SQL logic error.
                self.conn.commit()
        except Exception:
            pass  # Не критично, не ломаем запуск

    # ---- Nodes CRUD ----

    def save_node(self, node: Node, auto_embed: bool = False, auto_summary: bool = True):
        """Сохранить или обновить узел."""
        now = datetime.utcnow().isoformat()
        # Auto-generate summary for long nodes
        if auto_summary and node.content and len(node.content) > 500:
            meta = node.metadata if isinstance(node.metadata, dict) else json.loads(node.metadata) if node.metadata else {}
            if not meta.get('summary'):
                summary = self._generate_summary(node.content)
                if summary:
                    meta['summary'] = summary
                    node.metadata = meta
        # Удаляем старую FTS-запись если узел обновляется (INSERT OR REPLACE = DELETE + INSERT)
        self.conn.execute("DELETE FROM nodes_fts WHERE node_id = ?", (node.id,))
        self.conn.execute(
            """INSERT OR REPLACE INTO nodes
            (id, content, node_type, embedding, context, metadata, importance,
             tags, source, project, verified, access_count, status, created_at, updated_at, last_accessed, history)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                node.id, node.content, node.node_type,
                json.dumps(node.embedding.tolist() if hasattr(node.embedding, 'tolist') else node.embedding) if node.embedding is not None else None,
                json.dumps(node.context), json.dumps(node.metadata),
                node.importance, json.dumps(node.tags),
                node.source, node.project, node.verified, node.access_count, node.status,
                node.created_at, now, node.last_accessed,
                json.dumps(node.history),
            ),
        )
        # Auto-generate fastembed embedding if requested
        if auto_embed and node.content:
            self._generate_and_save_embedding(node.id, node.content)
        self.conn.commit()

    def _generate_summary(self, content: str, max_length: int = 200) -> Optional[str]:
        """Сгенерировать краткое содержание (перенаправлено на внешнюю модель)."""
        # Мы больше не грузим Llama здесь. Саммари будет запрашиваться через API
        # или откладываться до момента простоя системы.
        return content[:max_length] + "..."

    def _generate_and_save_embedding(self, node_id: str, content: str):
        """Сгенерировать embedding через fastembed и сохранить. Ленивая загрузка модели."""
        try:
            from fastembed import TextEmbedding
            if not hasattr(self, '_embed_model') or self._embed_model is None:
                self._embed_model = TextEmbedding(
                    model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
                )
            embeddings = list(self._embed_model.embed([content]))
            if embeddings:
                import numpy as np
                emb_bytes = embeddings[0].astype(np.float32).tobytes()
                self.save_embedding(node_id, emb_bytes, dim=len(embeddings[0]))
        except Exception as e:
            # Non-critical: embedding failure should not break node save
            import sys
            print(f"[storage] Embedding generation failed for {node_id}: {e}", file=sys.stderr)

    def get_node(self, node_id: str) -> Optional[Node]:
        """Получить узел по ID."""
        row = self.conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
        if not row:
            return None
        return self._row_to_node(row)

    def delete_node(self, node_id: str) -> bool:
        """Удалить узел и все его связи. Удаление из FTS — вручную."""
        self.conn.execute("DELETE FROM edges WHERE source_id = ? OR target_id = ?", (node_id, node_id))
        self.conn.execute("DELETE FROM node_embeddings WHERE node_id = ?", (node_id,))
        # node_contexts может не существовать в некоторых базах
        try:
            self.conn.execute("DELETE FROM node_contexts WHERE node_id = ?", (node_id,))
        except sqlite3.OperationalError:
            pass
        self.conn.execute("DELETE FROM nodes_fts WHERE node_id = ?", (node_id,))
        cur = self.conn.execute('DELETE FROM "nodes" WHERE "id" = ?', (node_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def list_nodes(
        self,
        node_type: str = None,
        project: str = None,
        status: str = "active",
        limit: int = 100,
        offset: int = 0,
    ) -> list[Node]:
        """Список узлов с фильтрами."""
        query = "SELECT * FROM nodes WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if node_type:
            query += " AND node_type = ?"
            params.append(node_type)
        if project:
            query += " AND project = ?"
            params.append(project)
        query += " ORDER BY importance DESC, created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_node(r) for r in rows]

    def count_nodes(self, node_type: str = None, project: str = None) -> int:
        """Количество узлов."""
        query = "SELECT COUNT(*) FROM nodes WHERE status = 'active'"
        params = []
        if node_type:
            query += " AND node_type = ?"
            params.append(node_type)
        if project:
            query += " AND project = ?"
            params.append(project)
        return self.conn.execute(query, params).fetchone()[0]

    def list_long_nodes(self, threshold: int = 1000, limit: int = 50) -> list[Node]:
        """Список длинных узлов (content > threshold) для context compression."""
        rows = self.conn.execute(
            "SELECT * FROM nodes WHERE length(content) > ? AND status = 'active' ORDER BY length(content) DESC LIMIT ?",
            (threshold, limit),
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def search_nodes_text(self, text: str, limit: int = 20) -> list[Node]:
        """Полнотекстовый поиск по content (FTS5 с fallback на LIKE)."""
        # Строим безопасный FTS5-запрос: слова через OR, экранирование кавычками
        import re as _re
        words = _re.findall(r"[\w]+", text, _re.UNICODE)
        # Пробуем FTS5
        if words:
            fts_query = " OR ".join(f'"{w}"' for w in words)
            try:
                rows = self.conn.execute(
                    """SELECT n.* FROM nodes_fts f
                       JOIN nodes n ON n.id = f.node_id
                       WHERE nodes_fts MATCH ? AND n.status = 'active'
                       ORDER BY rank LIMIT ?""",
                    (fts_query, limit),
                ).fetchall()
                if rows:
                    return [self._row_to_node(r) for r in rows]
            except Exception:
                pass
        # Fallback на LIKE
        rows = self.conn.execute(
            "SELECT * FROM nodes WHERE status = 'active' AND content LIKE ? ORDER BY importance DESC LIMIT ?",
            (f"%{text}%", limit),
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def search_nodes_fts_ranked(self, text: str, limit: int = 20) -> list[dict]:
        """FTS5 поиск с bm25 ranking. Возвращает [{node_id, rank, project}, ...].

        Многословный запрос соединяется через OR (а не AND по умолчанию),
        чтобы находить узлы содержащие ЛЮБОЕ из слов. Спецсимволы FTS5
        экранируются — каждое слово оборачивается в двойные кавычки.
        """
        # Строим безопасный FTS5-запрос: разбиваем на слова, чистим, OR
        import re as _re
        # Извлекаем слова (буквы/цифры, в т.ч. кириллица), отбрасываем спецсимволы FTS5
        words = _re.findall(r"[\w]+", text, _re.UNICODE)
        if not words:
            return []
        # Каждое слово в кавычках (экранирует операторы), соединяем через OR
        fts_query = " OR ".join(f'"{w}"' for w in words)
        try:
            rows = self.conn.execute(
                """SELECT f.node_id, f.rank, f.project
                   FROM nodes_fts f
                   JOIN nodes n ON n.id = f.node_id
                   WHERE nodes_fts MATCH ? AND n.status = 'active'
                   ORDER BY f.rank LIMIT ?""",
                (fts_query, limit),
            ).fetchall()
            return [{"node_id": r["node_id"], "rank": r["rank"], "project": r["project"]} for r in rows]
        except Exception:
            return []

    # ---- Embeddings CRUD ----

    # save_embedding is defined below (after vec search methods) to sync with vec table

    def get_embedding(self, node_id: str) -> Optional[bytes]:
        """Получить embedding узла."""
        row = self.conn.execute(
            "SELECT embedding FROM node_embeddings WHERE node_id = ?", (node_id,)
        ).fetchone()
        return row["embedding"] if row else None

    def delete_embedding(self, node_id: str):
        """Удалить embedding узла."""
        self.conn.execute("DELETE FROM node_embeddings WHERE node_id = ?", (node_id,))
        self.conn.commit()

    def get_all_embeddings(self) -> list[dict]:
        """Получить все embeddings для построения индекса."""
        rows = self.conn.execute(
            "SELECT node_id, embedding, dim FROM node_embeddings"
        ).fetchall()
        return [{"node_id": r["node_id"], "embedding": r["embedding"], "dim": r["dim"]} for r in rows]

    def count_embeddings(self) -> int:
        """Количество embeddings."""
        return self.conn.execute("SELECT COUNT(*) FROM node_embeddings").fetchone()[0]

    # ---- sqlite-vec HNSW search ----

    def _init_vec_table(self):
        """Create sqlite-vec virtual table and sync with node_embeddings. Safe to call multiple times."""
        try:
            # Load sqlite-vec extension
            self.conn.enable_load_extension(True)
            import sqlite_vec
            sqlite_vec.load(self.conn)
            self.conn.enable_load_extension(False)

            # Create virtual table
            self.conn.executescript(SQLITE_VEC_TABLE)

            # Sync: copy all embeddings from node_embeddings to vec table
            self._sync_vec_table()

            print(f"[storage] sqlite-vec initialized, {self.conn.execute('SELECT COUNT(*) FROM node_embeddings_vec').fetchone()[0]} vectors")
        except Exception as e:
            # sqlite-vec not available — fallback to brute-force
            print(f"[storage] sqlite-vec not available ({e}), using brute-force vector search")

    def _sync_vec_table(self):
        """Sync node_embeddings_vec with node_embeddings table."""
        try:
            # Clear and rebuild
            self.conn.execute("DELETE FROM node_embeddings_vec")
            rows = self.conn.execute(
                "SELECT node_id, embedding FROM node_embeddings"
            ).fetchall()
            for node_id, emb_bytes in rows:
                import numpy as np
                vec = np.frombuffer(emb_bytes, dtype=np.float32)
                # sqlite-vec expects JSON array or blob
                self.conn.execute(
                    "INSERT OR REPLACE INTO node_embeddings_vec(node_id, embedding) VALUES (?, ?)",
                    (node_id, emb_bytes)
                )
            self.conn.commit()
        except Exception as e:
            print(f"[storage] vec sync failed: {e}")

    def vector_search_fast(self, query_embedding: list, limit: int = 20, min_score: float = 0.0) -> list:
        """
        Fast vector search using sqlite-vec extension.
        Returns list of {node_id, score} sorted by similarity desc.
        Falls back to brute-force if sqlite-vec unavailable.
        """
        import numpy as np

        try:
            # Try sqlite-vec
            query_blob = np.array(query_embedding, dtype=np.float32).tobytes()
            rows = self.conn.execute(
                """
                SELECT node_id, distance
                FROM node_embeddings_vec
                WHERE embedding MATCH ?
                ORDER BY distance
                LIMIT ?
                """,
                (query_blob, limit * 2),  # fetch extra for post-filtering
            ).fetchall()

            results = []
            for row in rows:
                # sqlite-vec returns cosine distance (0=identical, 2=opposite)
                # Convert to similarity: sim = 1 - distance
                dist = row["distance"]
                sim = max(0.0, 1.0 - dist)
                if sim >= min_score:
                    results.append({"node_id": row["node_id"], "score": round(sim, 4)})

            return results[:limit]

        except Exception:
            # Fallback to brute-force
            return self._vector_search_brute(query_embedding, limit, min_score)

    def _vector_search_brute(self, query_embedding: list, limit: int = 20, min_score: float = 0.0) -> list:
        """Brute-force vector search (fallback)."""
        import numpy as np

        query_vec = np.array(query_embedding, dtype=np.float64)
        query_norm = float(np.linalg.norm(query_vec))

        all_embs = self.get_all_embeddings()
        results = []

        for item in all_embs:
            node_emb = np.frombuffer(item["embedding"], dtype=np.float32)
            dot = float(np.dot(query_vec, node_emb))
            norm = query_norm * float(np.linalg.norm(node_emb))
            if norm > 0:
                sim = dot / norm
                if sim >= min_score:
                    results.append({"node_id": item["node_id"], "score": round(sim, 4)})

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def save_embedding(self, node_id: str, embedding_bytes: bytes, dim: int = 384):
        """Save embedding to both node_embeddings and vec table."""
        self.conn.execute(
            "INSERT OR REPLACE INTO node_embeddings(node_id, embedding, dim) VALUES (?, ?, ?)",
            (node_id, embedding_bytes, dim),
        )
        # Also sync to vec table
        try:
            self.conn.execute(
                "INSERT OR REPLACE INTO node_embeddings_vec(node_id, embedding) VALUES (?, ?)",
                (node_id, embedding_bytes),
            )
        except Exception:
            pass  # vec table may not exist
        self.conn.commit()

    # ---- Edges CRUD ----

    def save_edge(self, edge: Edge):
        """Сохранить или обновить связь."""
        self.conn.execute(
            """INSERT OR REPLACE INTO edges
            (id, source_id, target_id, edge_type, weight, bidirectional,
             metadata, evidence_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                edge.id, edge.source_id, edge.target_id, edge.edge_type,
                edge.weight, int(edge.bidirectional),
                json.dumps(edge.metadata), edge.evidence_count,
                edge.created_at, edge.updated_at,
            ),
        )
        self.conn.commit()

    def get_edge(self, edge_id: str) -> Optional[Edge]:
        """Получить связь по ID."""
        row = self.conn.execute("SELECT * FROM edges WHERE id = ?", (edge_id,)).fetchone()
        if not row:
            return None
        return self._row_to_edge(row)

    def delete_edge(self, edge_id: str) -> bool:
        """Удалить связь."""
        cur = self.conn.execute('DELETE FROM "edges" WHERE "id" = ?', (edge_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def get_neighbors(self, node_id: str, direction: str = "both", edge_type: str = None, min_weight: float = 0.0) -> list[dict]:
        """Получить соседей узла с информацией о связи."""
        results = []
        queries = []

        if direction in ("out", "both"):
            q = "SELECT e.*, n.* FROM edges e JOIN nodes n ON e.target_id = n.id WHERE e.source_id = ? AND e.weight >= ? AND n.status = 'active'"
            params = [node_id, min_weight]
            if edge_type:
                q += " AND e.edge_type = ?"
                params.append(edge_type)
            q += " ORDER BY e.weight DESC"
            queries.append((q, params, "out"))

        if direction in ("in", "both"):
            q = "SELECT e.*, n.* FROM edges e JOIN nodes n ON e.source_id = n.id WHERE e.target_id = ? AND e.weight >= ? AND n.status = 'active'"
            params = [node_id, min_weight]
            if edge_type:
                q += " AND e.edge_type = ?"
                params.append(edge_type)
            q += " ORDER BY e.weight DESC"
            queries.append((q, params, "in"))

        for q, params, dir_ in queries:
            rows = self.conn.execute(q, params).fetchall()
            for row in rows:
                edge_data = {k: row[k] for k in ["id", "source_id", "target_id", "edge_type", "weight", "bidirectional", "evidence_count"]}
                node_data = {k: row[k] for k in ["id", "content", "node_type", "importance", "tags", "project"]}
                results.append({
                    "edge": edge_data,
                    "node": node_data,
                    "direction": dir_,
                })

        return results

    def get_edges_for_node(self, node_id: str) -> list[Edge]:
        """Все связи узла."""
        rows = self.conn.execute(
            "SELECT * FROM edges WHERE source_id = ? OR target_id = ? ORDER BY weight DESC",
            (node_id, node_id),
        ).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def count_edges(self) -> int:
        """Количество связей."""
        return self.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

    # ---- Stats ----

    def get_stats(self) -> dict:
        """Статистика графа."""
        nodes_total = self.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        nodes_active = self.conn.execute("SELECT COUNT(*) FROM nodes WHERE status = 'active'").fetchone()[0]
        edges_total = self.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        chunks_total = self.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        docs_total = self.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        projects_total = self.conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]

        types = {}
        for row in self.conn.execute("SELECT node_type, COUNT(*) FROM nodes WHERE status = 'active' GROUP BY node_type"):
            types[row[0]] = row[1]

        projects = {}
        for row in self.conn.execute("SELECT project, COUNT(*) FROM nodes WHERE status = 'active' GROUP BY project"):
            projects[row[0]] = row[1]

        return {
            "nodes_total": nodes_total,
            "nodes_active": nodes_active,
            "edges_total": edges_total,
            "chunks_total": chunks_total,
            "documents_total": docs_total,
            "projects_total": projects_total,
            "by_type": types,
            "by_project": projects,
            "db_path": self.db_path,
            "db_size_mb": round(os.path.getsize(self.db_path) / (1024 * 1024), 2),
        }

    # ---- Projects ----

    def save_project(self, project_id: str, name: str, description: str = None):
        """Сохранить проект."""
        self.conn.execute(
            "INSERT OR REPLACE INTO projects (id, name, description, updated_at) VALUES (?, ?, ?, datetime('now'))",
            (project_id, name, description),
        )
        self.conn.commit()

    def get_project(self, project_id: str) -> Optional[dict]:
        """Получить проект."""
        row = self.conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row:
            return dict(row)
        return None

    def list_projects(self) -> list[dict]:
        """Список проектов."""
        rows = self.conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
        return [dict(r) for r in rows]

    # ---- Documents ----

    def save_document(self, doc_id: str, project_id: str, source: str, file_type: str = None, file_size: int = None):
        """Сохранить документ."""
        self.conn.execute(
            """INSERT OR REPLACE INTO documents (id, project_id, source, file_type, file_size, indexed_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            (doc_id, project_id, source, file_type, file_size),
        )
        self.conn.commit()

    def get_document(self, doc_id: str) -> Optional[dict]:
        """Получить документ."""
        row = self.conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if row:
            return dict(row)
        return None

    def list_documents(self, project_id: str = None, limit: int = 100) -> list[dict]:
        """Список документов."""
        if project_id:
            rows = self.conn.execute("SELECT * FROM documents WHERE project_id = ? ORDER BY indexed_at DESC LIMIT ?", (project_id, limit)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM documents ORDER BY indexed_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ---- Chunks ----

    def save_chunk(self, chunk_id: str, document_id: str, project_id: str, content: str, position: int = 0, char_count: int = None):
        """Сохранить чанк."""
        self.conn.execute(
            """INSERT OR REPLACE INTO chunks (id, document_id, project_id, content, position, char_count)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (chunk_id, document_id, project_id, content, position, char_count or len(content)),
        )
        self.conn.commit()

    def get_chunk(self, chunk_id: str) -> Optional[dict]:
        """Получить чанк."""
        row = self.conn.execute("SELECT * FROM chunks WHERE id = ?", (chunk_id,)).fetchone()
        if row:
            return dict(row)
        return None

    def list_chunks(self, document_id: str = None, project_id: str = None, limit: int = 100) -> list[dict]:
        """Список чанков."""
        query = "SELECT * FROM chunks WHERE 1=1"
        params = []
        if document_id:
            query += " AND document_id = ?"
            params.append(document_id)
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        query += " ORDER BY position LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def search_chunks_fts(self, query: str, project_id: str = None, limit: int = 20) -> list[dict]:
        """Полнотекстовый поиск по чанкам (FTS5)."""
        if project_id:
            rows = self.conn.execute(
                """SELECT c.* FROM chunks c
                JOIN chunks_fts f ON c.id = f.chunk_id
                WHERE chunks_fts MATCH ? AND c.project_id = ?
                LIMIT ?""",
                (query, project_id, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT c.* FROM chunks c
                JOIN chunks_fts f ON c.id = f.chunk_id
                WHERE chunks_fts MATCH ?
                LIMIT ?""",
                (query, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---- Context heuristics ----

    @staticmethod
    def fill_context_heuristic(content: str) -> dict:
        """
        Заполнить контекстуальные измерения через эвристики (без LLM).
        Скорость: <0.01с на текст.

        Returns: {spatial, emotional, social, semantic, temporal}
        """
        import re
        from collections import Counter

        result = {"spatial": "", "emotional": "", "social": "", "semantic": "", "temporal": ""}
        if not content:
            return result

        text_lower = content.lower()
        content_orig = content

        # --- Spatial: IP, URL, города, серверы, хосты, locations ---
        ips = re.findall(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', content)
        urls = re.findall(r'https?://[^\s]+', content)
        # Русские города (в разных падежах)
        cities = re.findall(
            r'\b(Москв|Санкт-Петербург|Новосибирск|Екатеринбург|Казан|Нижн Новгород|'
            r'Челябинск|Самар|Омск|Ростов|Уф|Красноярск|Воронеж|Перм|Волгоград|'
            r'Лондон|Нью-Йорк|Берлин|Париж|Токио|Пекин|Сидней|Торонто|Лос-Анджелес|'
            r'Амстердам|Дублин|Вена|Прага|Варшава|Стамбул|Дубай|Сингапур|'
            r'Ростелеком|AWS|GCP|Azure|阿里云|Heroku|DigitalOcean|Hetzner|OVH|Selectel)',
            content, re.IGNORECASE
        )
        # Server/host patterns
        hosts = re.findall(r'\b(сервер|сервере|сервером|VPS|хост|хосте|облак|облаке|дата-центр|'
                          r'datacenter|node|кластер|кластере|инстанс|instance|контейнер|'
                          r'docker|kubernetes|k8s|нода|ноде|под|поде|deployment)\b',
                          content, re.IGNORECASE)
        spatial_parts = ips + urls + [c.title() for c in cities] + list(set(hosts))
        if spatial_parts:
            result["spatial"] = ", ".join(set(spatial_parts[:10]))

        # --- Temporal: даты, годы, относительное время ---
        text_no_ips = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '', content)
        dates = re.findall(r'\b(\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]\d{2,4})\b', text_no_ips)
        years = re.findall(r'\b(20\d{2})\b', text_no_ips)
        # Относительное время
        rel_time = re.findall(r'\b(сегодня|вчера|позавчера|последн недел|прошл недел|'
                             r'последн месяц|прошл месяц|сегодняшн|вчерашн|'
                             r'на днях|недавно|скоро|впоследствии|потом|сейчас|'
                             r'сначала|затем|потом|позже|раньше|в начале|в конце)\b',
                             content, re.IGNORECASE)
        temporal_parts = dates + years
        if rel_time:
            temporal_parts.append(rel_time[0].lower())
        if temporal_parts:
            result["temporal"] = ", ".join(set(temporal_parts[:10]))

        # --- Social: имена людей, роли, местоимения ---
        # Ищем "Имя Фамилия"
        names_full = re.findall(r'\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?\b', content)
        # Фильтруем не-имена
        non_names = {'Что', 'Как', 'Для', 'Это', 'Все', 'Они', 'Она', 'Он', 'Его', 'Её',
                     'Был', 'Были', 'Было', 'Есть', 'Могут', 'Может', 'Нужно', 'Надо',
                     'Хочет', 'Знает', 'Думает', 'Говорит', 'Считает', 'Работает',
                     'Проект', 'Система', 'Сервер', 'Данные', 'Модель', 'Граф',
                     'Узел', 'Ребро', 'База', 'Код', 'Тест', 'Файл', 'Папка',
                     'Время', 'День', 'Неделя', 'Месяц', 'Год', 'Сегодня', 'Вчера',
                     'Утро', 'Вечер', 'Ночь', 'Работа', 'Задача', 'Проблема',
                     'Решение', 'Вопрос', 'Ответ', 'Идея', 'План', 'Цель',
                     'Контекст', 'Измерение', 'Знание', 'Правило', 'Метод',
                     'Функция', 'Класс', 'Объект', 'Массив', 'Строка', 'Число'}
        names_full = [n for n in names_full if not any(w in non_names for w in n.split())]

        # Известные имена (русские)
        known_first = {'Alice', 'Bob', 'Charlie', 'Мария', 'Анна', 'Алексей', 'Дмитрий',
                       'Сергей', 'Андрей', 'Михаил', 'Ольга', 'Елена', 'Наталья',
                       'Татьяна', 'Светлана', 'Виктор', 'Николай', 'Владимир',
                       'Александр', 'Максим', 'Артём', 'Денис', 'Евгений', 'Кирилл',
                       'Павел', 'Роман', 'Тимур', 'Юрий', 'Ярослав', 'Василий',
                       'Григорий', 'Борис', 'Константин', 'Леонид', 'Марк', 'Олег',
                       'Руслан', 'Степан', 'Фёдор', 'Юлия', 'Алла', 'Вера',
                       'Людмила', 'Надежда', 'Валентина', 'Галина', 'Зоя',
                       'Инна', 'Ксения', 'Лариса', 'Маргарита', 'Полина',
                       'Раиса', 'Тамара', 'Ульяна', 'Яна', 'Жанна',
                       'Кристина', 'Дарья', 'Вероника', 'Ирина',
                       'Милана', 'Алиса', 'Варвара', 'Диана', 'Ева', 'Злата',
                       'Мира', 'Ника', 'Регина', 'Алекс'}
        # Одиночные имена
        single_names = re.findall(r'(?<=[\s,;:])[А-ЯЁ][а-яё]{2,8}(?=[\s,;:.])', ' ' + content + ' ')
        single_names = [sn for sn in single_names if sn in known_first and sn not in non_names]

        # Роли и сущности-люди
        roles = re.findall(r'\b(автор|разработчик|пользователь|клиент|заказчик|'
                          r'администратор|менеджер|руководитель|владелец|участник|'
                          r'OWL|User|ChatGPT|Claude|Copilot|разработчик CEO|'
                          r'предприниматель|инженер|фриланс|заказчик|преподаватель)\b',
                          content, re.IGNORECASE)

        all_social = names_full + single_names + [r.title() for r in roles]
        if all_social:
            result["social"] = ", ".join(set(all_social[:10]))

        # --- Emotional: тональность + эмоциональные маркеры ---
        positive_words = ['отлично', 'хорошо', 'прекрасно', 'замечательно', 'успех', 'радость',
                          'счастье', 'победа', 'достижение', 'прогресс', 'улучшение', 'рост',
                          'развитие', 'инновация', 'прорыв', 'эффективность', 'надёжность',
                          'стабильность', 'качество', 'оптимизация', 'ускорение', 'круто',
                          'супер', 'класс', 'прекрас', 'идеал', 'успешн', 'выигрыш',
                          'готово', 'завершён', 'работает', 'получилось', 'реализован',
                          'уникальн', 'мощн', 'гибк', 'прост', 'удобн']
        negative_words = ['плохо', 'ошибка', 'проблема', 'баг', 'фрустрирует', 'разочарование',
                          'провал', 'неудача', 'сложность', 'трудность', 'задержка', 'потеря',
                          'утечка', 'уязвимость', 'атака', 'взлом', 'крах', 'кризис',
                          'недостаток', 'ограничение', 'дефект', 'сбой', 'отказ',
                          'медленно', 'тяжело', 'сложно', 'невозможно', 'нельзя', 'опасно',
                          'страшно', 'ужас', 'кошмар', 'боль', 'грусть', 'печаль',
                          'лень', 'устал', 'устало', 'усталост', 'безысходн', 'тупик',
                          'запутан', 'запутанност', 'неразберихха', 'хаос', 'бардак',
                          'недоделан', 'недоделк', 'говно', 'хуйня', 'отстой', 'пиздец',
                          'бесит', 'злит', 'раздражает', 'заебало', 'надоело']
        # Позиция перед текстом для негативных слов (можем искать в начале строк)
        neg_prefix = re.findall(r'^(?:[-•*]\s*)?(?:❌|🔴|⛔|🚫)\s*(\w+)', content, re.MULTILINE)
        neg_prefix = [w for w in neg_prefix if w.lower() in negative_words or len(w) > 3]

        found_pos = [w for w in positive_words if w in text_lower]
        found_neg = [w for w in negative_words if w in text_lower]

        if found_pos and found_neg:
            result["emotional"] = f"mixed: +{','.join(found_pos[:3])}, -{','.join(found_neg[:3])}"
        elif found_pos:
            result["emotional"] = f"positive: {', '.join(found_pos[:5])}"
        elif found_neg:
            result["emotional"] = f"negative: {', '.join(found_neg[:5])}"

        # --- Semantic: ключевые слова (top-5 по частоте длинных слов) ---
        words = re.findall(r'\b[а-яёa-z]{4,}\b', text_lower)
        stopwords = {'который', 'этот', 'того', 'после', 'перед', 'между', 'через', 'когда',
                     'если', 'что', 'как', 'для', 'над', 'под', 'без', 'при', 'про', 'или',
                     'все', 'его', 'её', 'их', 'нас', 'вас', 'them', 'this', 'that', 'with',
                     'from', 'they', 'have', 'been', 'were', 'will', 'would', 'could', 'should',
                     'about', 'their', 'there', 'these', 'those', 'being', 'other', 'into',
                     'more', 'some', 'such', 'than', 'them', 'then', 'also', 'only', 'very',
                     'just', 'even', 'most', 'made', 'make', 'like', 'over', 'each', 'может',
                     'можеть', 'чтобы', 'время', 'можно', 'можетьб', 'здесь', 'здесьб',
                     'очень', 'будет', 'были', 'было', 'есть', 'этот', 'того', 'этом',
                     'котор', 'таким', 'такая', 'такие', 'такое', 'такое', 'таким',
                     'нужно', 'надо', 'стоит', 'значит', 'далее', 'также', 'потом'}
        filtered = [w for w in words if w not in stopwords and not w.isdigit()]
        if filtered:
            top = Counter(filtered).most_common(5)
            result["semantic"] = ", ".join([w for w, c in top])

        # Fallback: если social пуст но есть местоимения — ставим "author"
        if not result["social"]:
            prons = re.findall(r'\b(я|мы|мной|нами|мое|наш|наше|моё|сво|свои)\b', content, re.IGNORECASE)
            if prons:
                result["social"] = "author"

        # Fallback: если emotional пуст но есть пунктуация — грубый эвристик
        if not result["emotional"]:
            excl = content.count('!')
            ques = content.count('?')
            dots = content.count('...')
            if excl > 2:
                result["emotional"] = "excited"
            elif ques > 2:
                result["emotional"] = "questioning"

        return result

        return result

    # ---- Semantic Cache ----

    def get_cache(self, query: str) -> Optional[str]:
        """Получить ответ из кэша по тексту запроса."""
        import hashlib
        q_hash = hashlib.md5(query.lower().strip().encode()).hexdigest()
        row = self.conn.execute(
            "SELECT response_text FROM semantic_cache WHERE query_hash = ?", (q_hash,)
        ).fetchone()
        if row:
            self.conn.execute("UPDATE semantic_cache SET hits = hits + 1 WHERE query_hash = ?", (q_hash,))
            self.conn.commit()
            return row["response_text"]
        return None

    def save_cache(self, query: str, response: str):
        """Сохранить ответ в кэш."""
        import hashlib
        q_hash = hashlib.md5(query.lower().strip().encode()).hexdigest()
        self.conn.execute(
            "INSERT OR REPLACE INTO semantic_cache (query_hash, query_text, response_text) VALUES (?, ?, ?)",
            (q_hash, query, response)
        )
        self.conn.commit()

    # ---- Maintenance ----

    def archive_old_nodes(self, days: int = 90, min_importance: float = 0.2):
        """Архивировать старые неважные узлы."""
        self.conn.execute(
            """UPDATE nodes SET status = 'archived'
            WHERE status = 'active'
            AND importance < ?
            AND created_at < datetime('now', ?)""",
            (min_importance, f"-{days} days"),
        )
        self.conn.commit()

    def vacuum(self):
        """Оптимизировать БД."""
        self.conn.execute("VACUUM;")

    def close(self):
        self.conn.close()

    # ---- Helpers ----

    @staticmethod
    def _row_to_node(row) -> Node:
        n = Node(
            content=row["content"],
            node_type=row["node_type"],
            embedding=_decode_embedding(row["embedding"]),
            context=json.loads(row["context"]) if row["context"] else {},
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            importance=row["importance"],
            tags=json.loads(row["tags"]) if row["tags"] else [],
            node_id=row["id"],
            source=row["source"],
            project=row["project"],
        )
        n.access_count = row["access_count"] if "access_count" in row.keys() else 0
        n.status = row["status"] if "status" in row.keys() else "active"
        n.created_at = row["created_at"]
        n.updated_at = row["updated_at"]
        n.last_accessed = row["last_accessed"] if "last_accessed" in row.keys() else None
        n.history = json.loads(row["history"]) if "history" in row.keys() and row["history"] else []
        return n

    @staticmethod
    def _row_to_edge(row) -> Edge:
        return Edge(
            source_id=row["source_id"],
            target_id=row["target_id"],
            edge_type=row["edge_type"],
            weight=row["weight"],
            bidirectional=bool(row["bidirectional"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            edge_id=row["id"],
        )


# ---- Тесты ----

if __name__ == "__main__":
    import tempfile

    print("=== Тест Storage ===")
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    s = Storage(db_path)

    # Nodes
    n1 = Node(content="Тестовый узел 1", node_type="fact", importance=0.8, project="test")
    n2 = Node(content="Тестовый узел 2", node_type="concept", importance=0.6, project="test")
    s.save_node(n1)
    s.save_node(n2)
    print(f"Сохранено 2 узла")

    loaded = s.get_node(n1.id)
    assert loaded.content == n1.content
    print(f"Загружен: {loaded}")

    nodes = s.list_nodes(project="test")
    print(f"Список: {len(nodes)} узлов")

    # Edges
    e1 = Edge(n1.id, n2.id, edge_type="semantic", weight=0.9)
    s.save_edge(e1)
    print(f"Сохранена связь: {e1}")

    neighbors = s.get_neighbors(n1.id)
    print(f"Соседи n1: {len(neighbors)}")

    # Stats
    stats = s.get_stats()
    print(f"Статистика: {stats}")

    s.close()
    os.unlink(db_path)
    print("\n=== Все тесты Storage пройдены ===")
