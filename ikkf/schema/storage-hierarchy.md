# Storage Hierarchy — RAM / SSD / HDD

## Принцип
Не всё в RAM. Ленивая загрузка + кэширование.

## Уровни

| Уровень | Хранилище | Задержка | Объём | Что хранит |
|---|---|---|---|---|
| **L1: Hot Cache** | RAM | <1 мс | 100 MB | Активный контекст, горячие узлы |
| **L2: Warm Index** | SSD | 1-5 мс | 10 GB | Граф знаний, связи, индексы |
| **L3: Cold Archive** | SSD/HDD | 5-50 мс | 100 GB+ | Все факты, история, бэкапы |

## Реализация

### L1: Hot Cache (RAM)
```python
import threading
from collections import OrderedDict

class HotCache:
    """LRU кэш для горячих узлов. Максимум 50-100 MB RAM."""
    
    def __init__(self, max_mb=50):
        self.max_bytes = max_mb * 1024 * 1024
        self.current_bytes = 0
        self.cache = OrderedDict()
        self.lock = threading.Lock()
    
    def get(self, node_id):
        with self.lock:
            if node_id in self.cache:
                self.cache.move_to_end(node_id)
                node = self.cache[node_id]
                node.context.usage_count += 1
                node.context.last_accessed = now()
                return node
            return None
    
    def put(self, node):
        with self.lock:
            node_size = node.size_bytes()
            
            # Вытесняем старое если нет места
            while self.current_bytes + node_size > self.max_bytes and self.cache:
                _, old_node = self.cache.popitem(last=False)
                self.current_bytes -= old_node.size_bytes()
            
            self.cache[node.id] = node
            self.current_bytes += node_size
```

### L2: Warm Index (SSD) — SQLite граф
```sql
-- Основная таблица узлов
CREATE TABLE nodes (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding BLOB,
    created TIMESTAMP,
    updated TIMESTAMP,
    source TEXT,
    project TEXT,
    author TEXT,
    confidence REAL DEFAULT 1.0,
    usage_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMP,
    importance REAL DEFAULT 0.5,
    verified BOOLEAN DEFAULT 0
);

-- Связи графа
CREATE TABLE edges (
    id TEXT PRIMARY KEY,
    source_id TEXT REFERENCES nodes(id),
    target_id TEXT REFERENCES nodes(id),
    type TEXT NOT NULL,
    weight REAL DEFAULT 0.5,
    created TIMESTAMP,
    confidence REAL DEFAULT 1.0,
    bidirectional BOOLEAN DEFAULT 1
);

-- Теги
CREATE TABLE tags (
    node_id TEXT REFERENCES nodes(id),
    tag TEXT,
    PRIMARY KEY (node_id, tag)
);

-- Индексы
CREATE INDEX idx_nodes_project ON nodes(project);
CREATE INDEX idx_nodes_author ON nodes(author);
CREATE INDEX idx_nodes_importance ON nodes(importance);
CREATE INDEX idx_edges_source ON edges(source_id);
CREATE INDEX idx_edges_target ON edges(target_id);
CREATE INDEX idx_edges_type ON edges(type);

-- Полнотекстовый поиск
CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
    content,
    project,
    author,
    content=nodes,
    content_rowid=rowid
);
```

### L3: Cold Archive — файлы
```python
class ColdArchive:
    """Долгосрочное хранилище на диске. Все узлы которые не в кэше."""
    
    def __init__(self, path="/data/graph"):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        
        # SQLite для метаданных
        self.db_path = self.path / "graph.db"
        self.db = sqlite3.connect(str(self.db_path))
        self._init_db()
    
    def _init_db(self):
        self.db.executescript(SCHEMA_SQL)
        self.db.commit()
    
    def put(self, node):
        """Сохраняет узел в долгосрочное хранилище"""
        self.db.execute(
            "INSERT OR REPLACE INTO nodes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (node.id, node.type, node.content, node.embedding,
             node.context.created, node.context.updated,
             node.context.source, node.context.project,
             node.context.author, node.context.confidence,
             node.context.usage_count, node.context.last_accessed,
             node.metadata.importance, node.metadata.verified)
        )
        
        # Сохраняем связи
        for edge in node.edges:
            self.db.execute(
                "INSERT OR REPLACE INTO edges VALUES (?,?,?,?,?,?,?,?)",
                (edge.id, edge.source, edge.target, edge.type,
                 edge.weight, edge.context.created,
                 edge.context.confidence, edge.context.bidirectional)
            )
        
        self.db.commit()
    
    def get(self, node_id):
        """Загружает узел из долгосрочного хранилища"""
        cursor = self.db.execute(
            "SELECT * FROM nodes WHERE id = ?", (node_id,)
        )
        row = cursor.fetchone()
        if row:
            return Node.from_row(row)
        return None
    
    def search(self, query, filters=None, limit=20):
        """Поиск по долгосрочному хранилищу"""
        # Используем FTS5 для текстового поиска
        cursor = self.db.execute(
            "SELECT n.* FROM nodes n "
            "JOIN nodes_fts fts ON n.rowid = fts.rowid "
            "WHERE nodes_fts MATCH ? "
            "ORDER BY rank "
            "LIMIT ?",
            (query, limit)
        )
        return [Node.from_row(row) for row in cursor.fetchall()]
```

## Lazy Loading Pattern

```python
class TieredStorage:
    """Единый интерфейс для всех уровней хранения"""
    
    def __init__(self):
        self.hot = HotCache(max_mb=50)        # RAM
        self.warm = SQLiteGraph("/data/graph") # SSD
        self.cold = ColdArchive("/data/graph") # HDD
    
    def get(self, node_id):
        # L1: Проверяем кэш
        node = self.hot.get(node_id)
        if node:
            return node  # <1 мс
        
        # L2: Проверяем SQLite на SSD
        node = self.warm.get(node_id)
        if node:
            self.hot.put(node)  # Промоутим в кэш
            return node  # 1-5 мс
        
        # L3: Загружаем из архива
        node = self.cold.get(node_id)
        if node:
            self.warm.put(node)
            self.hot.put(node)
            return node  # 5-50 мс
        
        return None
    
    def put(self, node):
        # Сохраняем на все уровни
        self.cold.put(node)  # Всегда в архив
        self.warm.put(node)  # И в индекс
        
        # В кэш только если "горячий"
        if node.metadata.importance > 0.7 or node.context.usage_count > 5:
            self.hot.put(node)
```

## Экономия RAM

| Подход | RAM на 100K узлов |
|---|---|
| Всё в RAM (ChromaDB) | ~4 GB |
| Векторы + кэш | ~1.5 GB |
| Граф + lazy loading | **~200 MB** |

**Вывод:** Граф на диске + маленький кэш в RAM = в 20 раз меньше потребление памяти при том же объёме данных.
