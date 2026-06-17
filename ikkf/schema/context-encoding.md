# Context Encoding Schema

## Принцип
Каждый узел графа хранит контекст — не просто "что", но "когда", "где", "почему", "с чем связано".

## Структура контекста

### Временной контекст
```json
{
    "created": "2026-06-07T23:00:00Z",
    "updated": "2026-06-07T23:00:00Z",
    "last_accessed": null,
    "access_count": 0,
    "temporal_group": "2026-06-07"
}
```

### Пространственный контекст (источник)
```json
{
    "source": "telegram",
    "project": "spawnhere-memory",
    "author": "OWL",
    "file_path": null,
    "url": null,
    "position": null
}
```

### Семантический контекст
```json
{
    "topics": ["AI", "memory", "graph"],
    "entities": ["OWL", "IKKF", "ChromaDB"],
    "actions": ["проектирование", "сохранение"],
    "language": "ru"
}
```

### Эмоциональный контекст (важность)
```json
{
    "importance": 0.8,
    "confidence": 0.95,
    "emotional_weight": 0.5,
    "urgency": 0.3,
    "verified": false
}
```

### Социальный контекст
```json
{
    "author": "OWL",
    "contributors": ["Klim"],
    "audience": "private",
    "shared_with": []
}
```

## Индексация контекста

Для быстрого поиска по контексту создаём составные индексы:

```sql
-- По времени
CREATE INDEX idx_created ON nodes(context_created);
CREATE INDEX idx_temporal ON nodes(temporal_group);

-- По источнику
CREATE INDEX idx_project ON nodes(context_project);
CREATE INDEX idx_author ON nodes(context_author);

-- По важности
CREATE INDEX idx_importance ON nodes(metadata_importance);
CREATE INDEX idx_confidence ON nodes(context_confidence);

-- По тегам
CREATE INDEX idx_tags ON nodes(tags);

-- Полнотекстовый поиск по контенту
CREATE VIRTUAL TABLE nodes_fts USING fts5(content, tags);
```

## Поиск по контексту

```python
def search_by_context(query, context_filters):
    """
    Примеры запросов:
    - "все факты по проекту IKKF за сегодня"
    - "все факты с высокой важностью"
    - "все факты созданные OWL"
    """
    sql = "SELECT * FROM nodes WHERE 1=1"
    params = []
    
    if context_filters.get("project"):
        sql += " AND context_project = ?"
        params.append(context_filters["project"])
    
    if context_filters.get("author"):
        sql += " AND context_author = ?"
        params.append(context_filters["author"])
    
    if context_filters.get("min_importance"):
        sql += " AND metadata_importance >= ?"
        params.append(context_filters["min_importance"])
    
    if context_filters.get("date_from"):
        sql += " AND context_created >= ?"
        params.append(context_filters["date_from"])
    
    return db.execute(sql, params).fetchall()
```
