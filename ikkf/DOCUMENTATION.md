# IKKF Graph v2 — Документация

> **Версия:** 2.0
> **Дата:** 2026-06-08
> **Авторы:** Klim Bydancev + OWL (ZOO)
> **Порт:** 8766 (FastAPI)
> **БД:** SQLite (~6 MB)

---

## Содержание

1. [Обзор](#1-обзор)
2. [Архитектура](#2-архитектура)
3. [Установка](#3-установка)
4. [Быстрый старт](#4-быстрый-старт)
5. [Данные: узлы и связи](#5-данные-узлы-и-связи)
6. [Контекстуальные измерения](#6-контекстуальные-измерения)
7. [API Reference](#7-api-reference)
8. [RAG пайплайн](#8-rag-пайплайн)
9. [LLM интеграция](#9-llm-интеграция)
10. [Консолидация](#10-консолидация)
11. [Хранение](#11-хранение)
12. [Бенчмарки](#12-бенчмарки)
13. [Справочник файлов](#13-справочник-файлов)
14. [Устранение неполадок](#14-устранение-неполадок)

---

## 1. Обзор

**IKKF Graph** — граф знаний для AI-агентов. Хранит информацию в виде **узлов** (факты, концепты, действия, сущности) и **связей** между ними (8 типов). Каждый узел имеет **5 контекстуальных измерений** (когда, где, о чём, как, кто).

### Ключевые возможности

| Возможность | Описание |
|-------------|----------|
| **Граф знаний** | Узлы + связи, обход BFS/DFS, поиск путей |
| **Гибридный поиск** | Text + Vector + Context через один API |
| **RAG** | seed → expand → rank → context для LLM |
| **LLM-парсинг** | Автоматическая классификация, теги, сущности (Qwen 0.5B) |
| **Консолидация** | Ночная: дубликаты, архивация, переоценка важности |
| **Предиктивная подгрузка** | 2 хопа по графу для предсказания связанных узлов |
| **Самодостаточность** | Один файл SQLite, установка одной командой |

### Текущее состояние (08.06.2026)

```
325 узлов (6 типов)
1692 связей (8 типов)
312 чанков с FTS5
147 документов
8 проектов
6.3 MB размер БД
18 API эндпоинтов
```

---

## 2. Архитектура

### Слои

```
┌─────────────────────────────────────────────────┐
│  API (FastAPI, порт 8766)                       │
│  18 REST эндпоинтов                             │
├─────────────────────────────────────────────────┤
│  Graph (graph.py)                               │
│  CRUD, BFS/DFS, path, vector search, predict    │
├─────────────────────────────────────────────────┤
│  Storage (storage.py)                           │
│  SQLite + FTS5 + L1 LRU cache                   │
├─────────────────────────────────────────────────┤
│  Node / Edge (node.py)                          │
│  8 типов узлов, 8 типов связей, 5 context dims  │
├─────────────────────────────────────────────────┤
│  SQLite (graph.db, ~6 MB)                       │
│  nodes, edges, node_contexts, chunks, documents │
└─────────────────────────────────────────────────┘
```

### Иерархия хранения (L1/L2/L3)

| Уровень | Где | Скорость | Что хранит |
|---------|-----|----------|-----------|
| **L1** | RAM (dict) | ~0.003ms | Горячие узлы (до 1000) |
| **L2** | SQLite на SSD | ~0.4ms | Все узлы и связи |
| **L3** | Архив (status=archived) | ~5ms | Старые неактивные узлы |

### Файловая структура

```
i-know-kung-fu/
├── graph/                    # Основной код
│   ├── __init__.py
│   ├── node.py               # Node + Edge классы
│   ├── storage.py            # SQLite backend
│   ├── graph.py              # Основной класс Graph
│   ├── api.py                # FastAPI сервер
│   ├── graph_rag.py          # RAG пайплайн
│   ├── kungfu_llm.py         # Qwen 0.5B интеграция
│   ├── predictive.py         # Предиктивная подгрузка
│   ├── consolidation.py      # Ночная консолидация
│   ├── benchmark.py          # Бенчмарки
│   ├── migrate_to_graph.py   # Миграция из v1
│   ├── integration.py        # Гибридный поиск (v1 + v2)
│   ├── requirements.txt      # Зависимости
│   ├── install.sh            # Скрипт установки
│   ├── consolidate.sh        # Скрипт консолидации (cron)
│   ├── ikkf-graph.service    # systemd unit
│   ├── SKILL.md              # Инструкция для Hermes
│   ├── README.md             # Краткое описание
│   ├── DESIGN_v2.md          # Дизайн-документ (47KB)
│   ├── IMPLEMENTATION_PLAN.md # План реализации (572 строки)
│   └── schema/               # JSON-схемы
│       ├── node.json
│       ├── edge.json
│       ├── consolidation.md
│       ├── context-encoding.md
│       ├── predictive-preload.md
│       └── storage-hierarchy.md
├── data/
│   ├── graph.db              # Основная БД (6.3 MB)
│   ├── graph.db-wal          # WAL файл
│   └── graph.db-shm          # Shared memory
├── models/
│   └── Qwen2.5-0.5B-Instruct-Q4_K_M.gguf  # LLM (468 MB)
└── ideas/                    # Идеи и концепции
```

---

## 3. Установка

### Требования

- Python 3.10+
- pip
- ~500 MB места (без модели: ~10 MB)

### Быстрая установка

```bash
# Клонировать или скопировать папку graph/
cd i-know-kung-fu/graph

# Вариант 1: автоматический скрипт
bash install.sh

# Вариант 2: вручную
pip3 install fastapi uvicorn
mkdir -p data models

# Опционально: LLM для парсинга
pip3 install llama-cpp-python
wget -O models/Qwen2.5-0.5B-Instruct-Q4_K_M.gguf \
  https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf
```

### Проверка

```bash
python3 -c "from graph.graph import Graph; g = Graph(); print(g.stats()); g.close()"
```

### systemd (автозапуск)

```bash
sudo cp graph/ikkf-graph.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ikkf-graph
sudo systemctl start ikkf-graph
```

---

## 4. Быстрый старт

### Запуск сервера

```bash
# Напрямую
python3 -m graph.api

# Через uvicorn
uvicorn graph.api:app --host 127.0.0.1 --port 8766

# Через systemd
systemctl start ikkf-graph
```

### Первые шаги

```bash
# 1. Проверить что работает
curl http://127.0.0.1:8766/health
# → {"status":"ok","service":"ikkf-graph-api","version":"1.0"}

# 2. Создать узел
curl -s -X POST http://127.0.0.1:8766/node \
  -H "Content-Type: application/json" \
  -d '{
    "content": "IKKF — граф знаний для AI-агентов",
    "node_type": "concept",
    "importance": 0.9,
    "tags": ["ikkf", "граф"],
    "project": "default"
  }'

# 3. Поиск
curl -s "http://127.0.0.1:8766/search?q=IKKF&search_type=hybrid&limit=5"

# 4. Статистика
curl -s http://127.0.0.1:8766/stats
```

### Python API

```python
from graph.graph import Graph

g = Graph()

# Создать узел
n1 = g.add_node("User works with AI Agent", node_type="fact", importance=0.9)
n2 = g.add_node("Hermes — AI агент", node_type="concept", importance=0.8)

# Создать связь
g.add_edge(n1.id, n2.id, "semantic", 0.9)

# Поиск
results = g.search_text("Hermes")

# BFS — найти соседей на глубину 2
neighbors = g.bfs(n1.id, max_depth=2)

# Путь между узлами
path = g.find_path(n1.id, n2.id)

# Предсказание
predicted = g.predict_related(n1.id)

g.close()
```

---

## 5. Данные: узлы и связи

### Типы узлов (6)

| Тип | Описание | Пример |
|-----|----------|--------|
| `fact` | Факт, проверяемое утверждение | "IKKF использует SQLite" |
| `entity` | Сущность: человек, проект, инструмент | "User", "MacBook Pro 2012" |
| `action` | Действие: что-то было сделано | "Установил Ubuntu 24.04" |
| `concept` | Концепция: идея, определение | "Граф знаний — это..." |
| `event` | Событие: произошло в определённое время | "Сообщение от 2026-06-08" |
| `project` | Проект-контейнер | "project_deepseek" |

### Структура узла (Node)

```python
class Node:
    id: str              # UUID
    content: str         # Текст (до 10000 символов)
    node_type: str       # fact/concept/action/entity/event/project
    embedding: list[float]  # Вектор (384 dim, опционально)
    context: dict        # {temporal, spatial, semantic, emotional, social}
    metadata: dict       # Произвольные метаданные
    importance: float    # 0.0 - 1.0 (расчётный)
    tags: list[str]      # Теги для поиска
    source: str          # Источник: api/conversation/file
    project: str         # Проект-контейнер
    access_count: int    # Сколько раз запрашивался
    status: str          # active/archived/deleted
    created_at: str      # ISO timestamp
    updated_at: str      # ISO timestamp
    last_accessed: str   # ISO timestamp
```

### Типы связей (8)

| Тип | Описание | Направление |
|-----|----------|-------------|
| `semantic` | Семантическая связь (похож по смыслу) | Двунаправленная |
| `temporal` | Временная (до/после) | Направленная |
| `causal` | Причинно-следственная (вызывает/вызван) | Направленная |
| `associative` | Ассоциативная (общий контекст) | Двунаправленная |
| `hierarchical` | Иерархический (родитель/потомок) | Направленная |
| `contextual` | Контекстуальный (тот же контекст) | Двунаправленная |
| `similarity` | Похожесть (векторная близость) | Двунаправленная |
| `sequence` | Последовательность (шаг за шагом) | Направленная |

### Структура связи (Edge)

```python
class Edge:
    id: str              # UUID
    source_id: str       # ID исходного узла
    target_id: str       # ID целевого узла
    edge_type: str       # Тип связи (8 вариантов)
    weight: float        # 0.0 - 1.0 (сила связи)
    bidirectional: bool  # Двунаправленная?
    metadata: dict       # Произвольные метаданные
    evidence_count: int  # Сколько раз связь подтверждена
    created_at: str      # ISO timestamp
    updated_at: str      # ISO timestamp
```

### Схема SQLite

```sql
-- Основные таблицы
CREATE TABLE nodes (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    node_type TEXT NOT NULL DEFAULT 'fact',
    embedding BLOB,                    -- JSON array
    context TEXT DEFAULT '{}',         -- JSON {temporal, spatial, ...}
    metadata TEXT DEFAULT '{}',        -- JSON
    importance REAL DEFAULT 0.5,
    tags TEXT DEFAULT '[]',            -- JSON array
    source TEXT DEFAULT 'api',
    project TEXT DEFAULT 'default',
    access_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_accessed TEXT
);

CREATE TABLE edges (
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

CREATE TABLE node_contexts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL,
    context_dim TEXT NOT NULL,         -- temporal/spatial/semantic/emotional/social
    value TEXT,
    FOREIGN KEY (node_id) REFERENCES nodes(id),
    UNIQUE(node_id, context_dim)
);

-- Совместимость со старым IKKF
CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT, description TEXT, ...);
CREATE TABLE documents (id TEXT PRIMARY KEY, project_id TEXT, source TEXT, ...);
CREATE TABLE chunks (id TEXT PRIMARY KEY, document_id TEXT, content TEXT, ...);
CREATE VIRTUAL TABLE chunks_fts USING fts5(content, chunk_id, document_id, project_id);

-- Индексы
CREATE INDEX idx_nodes_type ON nodes(node_type);
CREATE INDEX idx_nodes_project ON nodes(project);
CREATE INDEX idx_nodes_importance ON nodes(importance DESC);
CREATE INDEX idx_edges_source ON edges(source_id);
CREATE INDEX idx_edges_target ON edges(target_id);
CREATE INDEX idx_edges_type ON edges(edge_type);
CREATE INDEX idx_ctx_dim ON node_contexts(context_dim);
CREATE INDEX idx_ctx_val ON node_contexts(value);
```

---

## 6. Контекстуальные измерения

Каждый узел имеет 5 измерений контекста:

| Измерение | Вопрос | Пример | Заполнено |
|-----------|--------|--------|-----------|
| `temporal` | Когда? | "2026-06", "июнь 2026" | 23 узла |
| `spatial` | Где? | "сервер", "MacBook" | 0 (LLM) |
| `semantic` | О чём? | "разработка", "IKKF" | 312 узлов |
| `emotional` | Как (тон)? | "positive", "negative" | 0 (LLM) |
| `social` | Кто? | "User", "AI" | 0 (LLM) |

### Хранение

Контекст хранится в двух местах:

1. **JSON в `nodes.context`** — для быстрого чтения узла
2. **Таблица `node_contexts`** — для поиска по измерениям

```sql
-- Поиск узлов по контексту
SELECT n.* FROM nodes n
JOIN node_contexts nc ON n.id = nc.node_id
WHERE nc.context_dim = 'semantic' AND nc.value LIKE '%разработка%';
```

### Заполнение через LLM

```bash
# Заполнить spatial/emotional/social для 20 узлов
curl -s -X POST http://127.0.0.1:8766/fill-context \
  -H "Content-Type: application/json" \
  -d '{"limit": 20}'

# Для конкретных узлов
curl -s -X POST http://127.0.0.1:8766/fill-context \
  -H "Content-Type: application/json" \
  -d '{"node_ids": ["uuid1", "uuid2"]}'
```

---

## 7. API Reference

### Базовые

```
GET /health          — {"status": "ok", "service": "ikkf-graph-api", "version": "1.0"}
GET /stats           — Статистика: nodes, edges, chunks, by_type, by_project
```

### Узлы

```
POST   /node              — Создать узел
GET    /node/{id}         — Получить узел по ID
GET    /nodes             — Список узлов (?type=&project=&status=&limit=&offset=)
PUT    /node/{id}         — Обновить узел
DELETE /node/{id}         — Удалить узел (+ все связи)
```

**POST /node** — тело:
```json
{
  "content": "Текст факта",
  "node_type": "fact",
  "importance": 0.8,
  "tags": ["тег1", "тег2"],
  "project": "default",
  "context": {"temporal": "2026-06", "semantic": "разработка"},
  "embedding": [0.1, 0.2, ...]
}
```

### Связи

```
POST   /edge              — Создать связь
GET    /edge/{id}         — Получить связь
DELETE /edge/{id}         — Удалить связь
GET    /neighbors/{id}    — Соседи (?direction=in|out|both&edge_type=&min_weight=)
GET    /path/{from}/{to}   — Путь между узлами (?max_depth=5)
```

**POST /edge** — тело:
```json
{
  "source_id": "uuid",
  "target_id": "uuid",
  "edge_type": "semantic",
  "weight": 0.7,
  "bidirectional": true
}
```

### Поиск

```
GET /search?q={query}&search_type={text|vector|hybrid|context}&project=&limit=
GET /context?q={query}&depth=2&min_weight=0.3&limit=5     — Контекст по тексту
GET /context/{node_id}?depth=2&min_weight=0.3              — Контекст узла (BFS)
GET /predict/{node_id}?limit=10                            — Предсказание (2 хопа)
```

**GET /search** — search_type:
- `text` — LIKE '%query%' по content
- `vector` — cosine similarity по embedding
- `hybrid` — text + vector (рекомендуется)
- `context` — поиск по контексту (semantic=query)

### RAG + LLM

```
POST /rag              — RAG запрос
POST /parse            — Парсинг текста через LLM
POST /fill-context     — Заполнение контекста через LLM
```

**POST /rag** — тело:
```json
{
  "query": "Что такое IKKF?",
  "project": "default",
  "max_nodes": 10,
  "max_depth": 2,
  "min_weight": 0.3
}
```

**POST /parse** — тело:
```json
{
  "text": "User installed Ubuntu 24.04",
  "project": "default"
}
```

### Совместимость (старый IKKF)

```
GET    /projects          — Список проектов
POST   /project           — Создать проект
GET    /project/{id}      — Получить проект
GET    /documents         — Список документов (?project_id=)
POST   /document          — Создать документ
GET    /chunks            — Список чанков (?document_id=&project_id=)
POST   /chunk             — Создать чанк
GET    /search/chunks?q=  — FTS5 поиск по чанкам
```

### Обслуживание

```
POST /consolidate      — Запустить консолидацию
```

---

## 8. RAG пайплайн

### Алгоритм

```
Вопрос → Seed → Expand → Rank → Context
```

### Шаг 1: Seed (поиск начальных узлов)

1. **FTS5 по чанкам** — полнотекстовый поиск по `chunks_fts`
2. **Text search по узлам** — `LIKE '%query%'` по `nodes.content`
3. **Keyword search** — разбиение вопроса на слова, поиск каждого
4. **Vector search** — cosine similarity (если есть embedding)

### Шаг 2: Expand (расширение через граф)

BFS от каждого seed-узла:
- Глубина: до `max_depth` (по умолчанию 2)
- Минимальный вес связи: `min_weight` (по умолчанию 0.3)
- Собирает все узлы на пути

### Шаг 3: Rank (ранжирование)

Формула:
```
score = depth_score * 0.3 + importance * 0.3 + edge_weight * 0.2 + access_score * 0.1 + seed_bonus
```

Где:
- `depth_score = 1.0 / (1 + depth)` — ближе к seed = лучше
- `importance` — важность узла
- `edge_weight` — вес связи
- `access_score = min(1.0, access_count / 10.0)` — популярность
- `seed_bonus = 0.1` — бонус для seed-узлов

### Шаг 4: Context (формирование текста)

```
=== Контекст из графа знаний ===

1. [fact] Текст факта
   Теги: тег1, тег2
   Когда: 2026-06
   Тема: разработка

2. [concept] Другой факт
   ...
```

### Использование

```python
from graph.graph import Graph
from graph.graph_rag import GraphRAG

g = Graph()
rag = GraphRAG(g)

result = rag.query(
    question="Что такое IKKF?",
    max_context_nodes=10,
    max_depth=2,
    min_weight=0.3,
    project="default"
)

print(result["context_text"])
# === Контекст из графа знаний ===
# 1. [concept] IKKF — граф знаний для AI-агентов
#    Тема: разработка
# ...

g.close()
```

---

## 9. LLM интеграция

### Модель

- **Qwen 2.5 0.5B Instruct** (Q4_K_M quantization)
- Размер: 468 MB
- Контекст: 512 токенов (для скорости на CPU)
- Потока: 2 (для сервера с 2 CPU)

### Возможности

| Метод | Что делает | Время (CPU) |
|-------|-----------|-------------|
| `classify_node(text)` | Классификация типа узла | ~20s |
| `rate_importance(text)` | Оценка важности 0.0-1.0 | ~15s |
| `generate_tags(text)` | Генерация тегов | ~20s |
| `extract_entities(text)` | Извлечение сущностей | ~25s |
| `should_merge(t1, t2)` | Нужно ли объединить узлы | ~20s |

### API endpoints

**POST /parse** — полный парсинг текста:
```bash
curl -s -X POST http://127.0.0.1:8766/parse \
  -H "Content-Type: application/json" \
  -d '{"text": "User installed Ubuntu 24.04", "project": "default"}'
```

Ответ:
```json
{
  "node_id": "uuid",
  "classification": {"type": "action", "confidence": 0.8, "reason": "..."},
  "importance": 0.75,
  "tags": ["ubuntu", "macbook", "установка"],
  "entities": [{"name": "User", "type": "person"}, {"name": "Ubuntu 24.04", "type": "tool"}],
  "entity_node_ids": ["uuid1", "uuid2"]
}
```

**POST /fill-context** — заполнение контекстуальных измерений:
```bash
curl -s -X POST http://127.0.0.1:8766/fill-context \
  -H "Content-Type: application/json" \
  -d '{"limit": 20}'
```

### Примечания

- LLM работает на CPU, поэтому медленная (~20s на запрос)
- Для интерактивной работы используйте LLM только для парсинга
- Для ночной консолидации — приемлемо
- Модель можно заменить на более мощную (поддерживается любая GGUF)

---

## 10. Консолидация

### Что делает

Ночной процесс (cron 3:00):

1. **Ослабление связей** — уменьшает вес старых неиспользуемых связей (decay 0.05 за 30 дней)
2. **Переоценка важности** — на основе access_count, количества связей, свежести
3. **Объединение дубликатов** — Jaccard similarity > 0.85 → merge
4. **Архивация** — узлы с importance < 0.2 и старше 90 дней → status=archived
5. **VACUUM** — оптимизация SQLite

### Формула важности

```
new_importance = old * 0.5 + access_bonus + edge_bonus + freshness

access_bonus = min(0.2, access_count * 0.02)
edge_bonus = min(0.2, edge_count * 0.05)
freshness = max(0, 0.1 - age_days * 0.001)
```

### Запуск

```bash
# Автоматически (cron 3:00)
crontab -l | grep ikkf
# 0 3 * * * /root/projects/i-know-kung-fu/graph/consolidate.sh

# Вручную
bash graph/consolidate.sh

# Через API
curl -s -X POST http://127.0.0.1:8766/consolidate

# Через Python
from graph.graph import Graph
from graph.consolidation import Consolidator
g = Graph()
c = Consolidator(g)
stats = c.run(full=True)
```

### С LLM

```python
from graph.kungfu_llm import KungFuLLM
llm = KungFuLLM(n_ctx=512, n_threads=2)
c = Consolidator(g, llm=llm)
stats = c.run(full=True, use_llm=True)  # + заполнение spatial/emotional/social
```

---

## 11. Хранение

### SQLite схема

```
graph.db (6.3 MB)
├── nodes (325 записей)
├── edges (1692 записей)
├── node_contexts (335 записей)
├── projects (8 записей)
├── documents (147 записей)
├── chunks (312 записей)
└── chunks_fts (FTS5 виртуальная таблица)
```

### Индексы

```
idx_nodes_type ON nodes(node_type)
idx_nodes_project ON nodes(project)
idx_nodes_importance ON nodes(importance DESC)
idx_edges_source ON edges(source_id)
idx_edges_target ON edges(target_id)
idx_edges_type ON edges(edge_type)
idx_ctx_dim ON node_contexts(context_dim)
idx_ctx_val ON node_contexts(value)
```

### WAL mode

```sql
PRAGMA journal_mode=WAL;     -- Write-Ahead Logging
PRAGMA foreign_keys=ON;      -- Внешние ключи
```

WAL позволяет читать пока идёт запись — важно для API.

---

## 12. Бенчмарки

Тесты на сервере (2 CPU, 3.8 GB RAM):

| Операция | Время | Примечание |
|----------|-------|-----------|
| Create node | 1.57ms | SQLite INSERT |
| Read node (L1 cache) | 0.003ms | RAM dict |
| Read node (L2 SQLite) | 0.4ms | Indexed query |
| Text search | 0.38ms | LIKE '%query%' |
| FTS5 search | 0.12ms | Full-text index |
| BFS (depth=2) | 0.10ms | ~50 узлов |
| BFS (depth=5) | 0.25ms | ~200 узлов |
| Path finding | 0.15ms | BFS, depth=5 |
| Vector search | 2.1ms | 300 узлов, cosine |
| RAG query | 6.34ms | seed+expand+rank |
| LLM classify | ~20,000ms | Qwen 0.5B на CPU |
| LLM importance | ~15,000ms | Qwen 0.5B на CPU |

---

## 13. Справочник файлов

| Файл | Назначение | Размер |
|------|-----------|--------|
| `graph/node.py` | Node + Edge классы | 9.6 KB |
| `graph/storage.py` | SQLite backend | 20 KB |
| `graph/graph.py` | Основной класс Graph | 13 KB |
| `graph/api.py` | FastAPI сервер | 22 KB |
| `graph/graph_rag.py` | RAG пайплайн | 12 KB |
| `graph/kungfu_llm.py` | Qwen 0.5B интеграция | 10 KB |
| `graph/predictive.py` | Предиктивная подгрузка | 8.8 KB |
| `graph/consolidation.py` | Ночная консолидация | 9.5 KB |
| `graph/benchmark.py` | Бенчмарки | 5 KB |
| `graph/migrate_to_graph.py` | Миграция из v1 | 6.5 KB |
| `graph/integration.py` | Гибридный поиск v1+v2 | 6.5 KB |
| `graph/requirements.txt` | Зависимости | 0.4 KB |
| `graph/install.sh` | Скрипт установки | 2 KB |
| `graph/consolidate.sh` | Скрипт консолидации | 0.8 KB |
| `graph/ikkf-graph.service` | systemd unit | 0.5 KB |
| `graph/SKILL.md` | Инструкция для Hermes | 7.3 KB |
| `graph/DESIGN_v2.md` | Дизайн-документ | 47 KB |
| `graph/IMPLEMENTATION_PLAN.md` | План реализации | 25 KB |

---

## 14. Устранение неполадок

### Сервис не запускается

```bash
# Проверить статус
systemctl status ikkf-graph.service

# Логи
journalctl -u ikkf-graph.service -n 50

# Проверить порт
ss -tlnp | grep 8766

# Ручной запуск (увидеть ошибки)
python3 -m graph.api
```

### Порт 8766 занят

```bash
# Найти процесс
ss -tlnp | grep 8766
lsof -i :8766

# Убить
kill -9 <PID>
```

### БД повреждена

```bash
# Проверить целостность
python3 -c "import sqlite3; conn = sqlite3.connect('data/graph.db'); print(conn.execute('PRAGMA integrity_check').fetchone())"

# Восстановить из бэкапа (если есть)
cp data/graph.db.bak data/graph.db
```

### LLM не загружается

```bash
# Проверить модель
ls -lh models/Qwen2.5-0.5B-Instruct-Q4_K_M.gguf

# Проверить llama-cpp
python3 -c "from llama_cpp import Llama; print('OK')"

# Если нет llama-cpp
pip3 install llama-cpp-python
```

### Медленный поиск

```bash
# Проверить индексы
python3 -c "
import sqlite3
conn = sqlite3.connect('data/graph.db')
for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='index'\"):
    print(r[0])
"

# Пересоздать FTS5
python3 -c "
import sqlite3
conn = sqlite3.connect('data/graph.db')
conn.execute('DROP TABLE IF EXISTS chunks_fts')
conn.execute('CREATE VIRTUAL TABLE chunks_fts USING fts5(content, chunk_id, document_id, project_id)')
# Переиндексировать...
"
```

### Старый IKKF (8765) мешает

```bash
# Убить процесс
kill -9 $(ss -tlnp | grep 8765 | grep -oP 'pid=\K\d+')

# Переименовать старый API
mv api.py api.py.old
```

---

## Приложения

### A. Миграция из IKKF v1

```bash
python3 -m graph.migrate_to_graph
```

Мигрирует: проекты, документы, чанки, векторы из старого IKKF (ChromaDB + SQLite) в Graph v2.

### B. Бэкап

```bash
# Просто скопировать файл БД
cp data/graph.db data/graph.db.backup.$(date +%Y%m%d)

# Или через SQLite
sqlite3 data/graph.db ".backup data/graph.db.backup"
```

### C. Экспорт данных

```bash
# JSON дамп всех узлов
python3 -c "
import sqlite3, json
conn = conn = sqlite3.connect('data/graph.db')
conn.row_factory = sqlite3.Row
nodes = [dict(r) for r in conn.execute('SELECT * FROM nodes').fetchall()]
print(json.dumps(nodes, ensure_ascii=False, indent=2))
" > nodes_export.json
```

### D. Добавление нового типа узла

1. Добавить в `NODE_TYPES` в `node.py`
2. Перезапустить API
3. Готово — SQLite не требует миграции (node_type — строка)

### E. Добавление нового типа связи

1. Добавить в `EDGE_TYPES` в `node.py`
2. Перезапустить API
3. Готово — SQLite не требует миграции (edge_type — строка)
