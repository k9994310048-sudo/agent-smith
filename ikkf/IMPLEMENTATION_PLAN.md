# I Know Kung Fu — Пошаговый план реализации

> Создано: 2026-06-07
> Статус: Черновик
> Версия: 1.0

---

## Фаза 0: Подготовка (1-2 дня)

### Шаг 0.1: Очистка диска сервера
- [ ] Удалить pip cache (~976MB): `rm -rf /root/.cache/pip`
- [ ] Удалить старый backup (~1.4GB): найти и удалить
- [ ] Удалить SQL dump (~190MB): найти и удалить
- **Ожидаемый результат:** +2.5GB свободного места
- **Риск:** Низкий (только кэши и бэкапы)
- **Проверка:** `df -h /` → должно быть >5GB free

### Шаг 0.2: Настройка окружения MacBook
- [ ] Подключиться к MacBook (когда доступ будет)
- [ ] Обновить систему: `sudo apt update && sudo apt upgrade -y`
- [ ] Установить базовые пакеты: `git curl wget build-essential python3 python3-pip python3-venv nodejs npm docker.io docker-compose`
- [ ] Установить VS Code: `sudo snap install code --classic`
- [ ] Создать рабочую директорию: `mkdir -p /home/mac/projects/i-know-kung-fu`
- **Ожидаемый результат:** MacBook готов к разработке
- **Проверка:** все команды выполняются без ошибок

### Шаг 0.3: Резервное копирование текущего IKKF
- [ ] Остановить API: `systemctl stop ikkf-api`
- [ ] Скопировать данные: `cp -r /root/projects/i-know-kung-fu/data /root/projects/i-know-kung-fu/data-backup-2026-06-07`
- [ ] Скопировать код: `cp -r /root/projects/i-know-kung-fu/*.py /root/projects/i-know-kung-fu/code-backup-2026-06-07/`
- [ ] Запустить API: `systemctl start ikkf-api`
- **Ожидаемый результат:** Полный бэкап текущей системы
- **Проверка:** `curl http://localhost:8765/health` → `{"status":"ok"}`

---

## Фаза 1: Граф знаний — Ядро (3-5 дней)

### Шаг 1.1: Создание структуры проекта
```
graph/
├── __init__.py
├── node.py          # Класс Node
├── edge.py          # Класс Edge
├── graph.py          # Основной граф (in-memory + persistence)
├── storage.py        # Слой хранения (SQLite backend)
├── search.py         # Поиск по графу (BFS/DFS/vector hybrid)
├── context.py        # Контекстное кодирование
├── predictive.py     # Предиктивная подгрузка
├── consolidation.py  # Ночной процесс консолидации
├── api.py            # FastAPI endpoints
├── migrate.py        # Миграция из ChromaDB
├── benchmark.py      # Бенчмарки
└── graph_rag.py      # RAG через граф
```
- **Ожидаемый результат:** Структура файлов создана
- **Проверка:** `ls -la graph/*.py` → 12 файлов

### Шаг 1.2: Реализация Node (узел графа)
```python
class Node:
    id: str              # UUID
    content: str         # Текст
    embedding: list[float]  # Вектор (384 dim от MiniLM)
    node_type: str       # fact / concept / event / skill / project / person / idea
    context: dict        # {temporal, spatial, semantic, emotional, social}
    metadata: dict       # {source, created, updated, version}
    importance: float    # 0.0 - 1.0 (расчётный)
    access_count: int    # Сколько раз запрашивался
    last_accessed: datetime
    tags: list[str]
    status: str          # active / archived / deleted
```
- Методы: `to_dict()`, `from_dict()`, `update_importance()`, `touch()`
- **Ожидаемый результат:** Класс Node с полным набором полей
- **Проверка:** `python3 -c "from graph.node import Node; n = Node(content='test'); print(n.id)"` → UUID

### Шаг 1.3: Реализация Edge (связь)
```python
class Edge:
    id: str
    source_id: str       # ID исходного узла
    target_id: str       # ID целевого узла
    edge_type: str       # semantic / temporal / causal / associative / hierarchical / contextual / similarity / sequence
    weight: float        # 0.0 - 1.0
    metadata: dict       # {created, updated, evidence_count}
    bidirectional: bool  # Двунаправленная ли связь
```
- Методы: `to_dict()`, `from_dict()`, `strengthen()`, `weaken()`
- **Ожидаемый результат:** Класс Edge с 8 типами связей
- **Проверка:** `python3 -c "from graph.edge import Edge; e = Edge('a','b','semantic',0.8); print(e.weight)"` → 0.8

### Шаг 1.4: Реализация Storage (SQLite backend)
```python
# Таблица nodes
CREATE TABLE nodes (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    embedding BLOB,           # JSON array
    node_type TEXT DEFAULT 'fact',
    context JSON,             # Контекстное кодирование
    metadata JSON,
    importance REAL DEFAULT 0.5,
    access_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMP,
    tags JSON,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

# Таблица edges
CREATE TABLE edges (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    weight REAL DEFAULT 0.5,
    metadata JSON,
    bidirectional BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES nodes(id),
    FOREIGN KEY (target_id) REFERENCES nodes(id)
);

# Индексы для быстрого поиска
CREATE INDEX idx_nodes_type ON nodes(node_type);
CREATE INDEX idx_nodes_status ON nodes(status);
CREATE INDEX idx_nodes_importance ON nodes(importance DESC);
CREATE INDEX idx_edges_source ON edges(source_id);
CREATE INDEX idx_edges_target ON edges(target_id);
CREATE INDEX idx_edges_type ON edges(edge_type);

# FTS5 полнотекстовый поиск
CREATE VIRTUAL TABLE nodes_fts USING fts5(
    content, tags,
    content='nodes',
    content_rowid='rowid'
);
```
- **Ожидаемый результат:** SQLite БД с индексами и FTS5
- **Проверка:** `sqlite3 data/graph.db ".tables"` → nodes, edges, nodes_fts

### Шаг 1.5: Реализация Graph (основной класс)
```python
class KnowledgeGraph:
    def __init__(self, db_path: str, max_memory_nodes: int = 10000)
    
    # CRUD
    def add_node(content, embedding=None, node_type='fact', context=None, tags=None) → Node
    def get_node(node_id) → Node | None
    def update_node(node_id, **kwargs) → Node
    def delete_node(node_id) → bool
    
    # Связи
    def add_edge(source_id, target_id, edge_type, weight=0.5) → Edge
    def get_edges(node_id, direction='both', edge_type=None) → list[Edge]
    def remove_edge(edge_id) → bool
    
    # Навигация
    def get_neighbors(node_id, depth=1) → list[Node]
    def bfs(start_id, max_depth=3, filter_fn=None) → list[Node]
    def dfs(start_id, max_depth=5, filter_fn=None) → list[Node]
    def find_path(source_id, target_id, max_depth=6) → list[Node]
    
    # Поиск
    def search(query, mode='hybrid', limit=10) → list[(Node, float)]
    def vector_search(query_embedding, limit=10) → list[(Node, float)]
    def keyword_search(query, limit=10) → list[(Node, float)]
    def context_search(context_filter, limit=10) → list[Node]
    
    # Статистика
    def stats() → dict
    
    # LRU кэш для RAM
    def _load_to_memory(node_id)
    def _evict_from_memory()
```
- **Ожидаемый результат:** Рабочий класс KnowledgeGraph
- **Проверка:** `python3 -c "from graph.graph import KnowledgeGraph; g = KnowledgeGraph(':memory:'); n = g.add_node('test'); print(n.id)"` → UUID

### Шаг 1.6: Реализация Context (контекстное кодирование)
```python
class ContextEncoder:
    def encode(temporal=None, spatial=None, semantic=None, emotional=None, social=None) → dict
    def decode(context_dict) → dict
    def similarity(ctx1, ctx2) → float  # 0.0 - 1.0
    
    # Автоматическое извлечение контекста из текста
    def extract_from_text(text) → dict
    # Использует простые эвристики:
    # - temporal: даты, время, "вчера", "завтра"
    # - spatial: города, страны, IP, "дома", "в офисе"
    # - semantic: категория по ключевым словам
    # - emotional: sentiment analysis (positive/negative/neutral)
    # - social: упоминания людей, организаций
```
- **Ожидаемый результат:** Контекстное кодирование работает
- **Проверка:** `python3 -c "from graph.context import ContextEncoder; e = ContextEncoder(); print(e.extract_from_text('Вчера в Москве встретился with user'))"`

### Шаг 1.7: Реализация Predictive (предиктивная подгрузка)
```python
class PredictiveCache:
    def __init__(self, graph: KnowledgeGraph, cache_size: int = 1000)
    
    def record_access(node_id: str)  # Записать доступ
    def predict_next(node_id: str, limit: int = 10) → list[str]  # Предсказать следующие
    def preload(node_ids: list[str])  # Предзагрузить в RAM
    def get_stats() → dict  # hit_rate, miss_rate, cache_size
    
    # Алгоритм:
    # 1. Построить transition_matrix[source][target] = count
    # 2. Нормализовать в вероятности
    # 3. При доступе к node → предзагрузить top-K соседей по вероятности
    # 4. LRU eviction при переполнении
```
- **Ожидаемый результат:** Предиктивная подгрузка снижает latency на 40-60%
- **Проверка:** `python3 -c "from graph.predictive import PredictiveCache; ..."`

### Шаг 1.8: Реализация Consolidation (ночная консолидация)
```python
class Consolidator:
    def __init__(self, graph: KnowledgeGraph)
    
    def run_full_cycle()  # Полный цикл консолидации
    def find_duplicates(threshold=0.95) → list[tuple]  # Найти дубликаты
    def merge_nodes(node_ids: list[str]) → Node  # Объединить узлы
    def discover_edges(threshold=0.7) → list[Edge]  # Обнаружить новые связи
    def create_abstractions() → list[Node]  # Создать абстракции
    def archive_old(days=90) → int  # Архивировать старое
    def calculate_importance() → None  # Пересчитать важность
    
    # Алгоритм важности (как PageRank):
    # importance(node) = 0.1 + 0.9 * Σ(edge.weight * importance(neighbor)) / degree(neighbor)
    # Итеративно, 10 итераций, convergence threshold 0.001
```
- **Ожидаемый результат:** Ночной cron запускает консолидацию
- **Проверка:** `python3 -c "from graph.consolidation import Consolidator; ..."`

---

## Фаза 2: API и интеграция (2-3 дня)

### Шаг 2.1: FastAPI endpoints (порт 8766)
```
GET  /                    → {status, version, stats}
GET  /health              → {status: "ok"}
GET  /stats               → {nodes, edges, cache_hit_rate, ...}

POST /nodes               → Create node {content, type, context, tags}
GET  /nodes/{id}          → Get node
PUT  /nodes/{id}          → Update node
DELETE /nodes/{id}        → Delete node
GET  /nodes               → List nodes (?type=&status=&limit=&offset=)

POST /edges               → Create edge {source, target, type, weight}
GET  /edges/{id}          → Get edge
DELETE /edges/{id}        → Delete edge
GET  /edges               → List edges (?node_id=&type=)

GET  /neighbors/{id}      → Get neighbors (?depth=&type=)
GET  /path/{source}/{target} → Find path (?max_depth=)
POST /search              → Search {query, mode, limit, context_filter}
GET  /context/{id}        → Get context cluster

POST /consolidate         → Trigger consolidation
POST /migrate             → Trigger migration from ChromaDB
```
- **Ожидаемый результат:** Все endpoints работают
- **Проверка:** `curl -X POST http://localhost:8766/nodes -d '{"content":"test"}'` → `{"id":"..."}`

### Шаг 2.2: Миграция из ChromaDB
```python
class ChromaDBMigrator:
    def __init__(self, chroma_path: str, graph: KnowledgeGraph)
    
    def migrate_all() → dict  # {migrated: N, errors: N, time: seconds}
    def migrate_batch(batch_size=100) → int  # Пакетная миграция
    def create_edges_from_similarity(threshold=0.7) → int  # Создать связи
    def verify_migration() → bool  # Проверить целостность
    
    # Процесс:
    # 1. Итерировать по всем chunks в ChromaDB
    # 2. Для каждого: создать Node в графе
    # 3. После миграции: создать Edge между похожими узлами
    # 4. Восстановить контекст из метаданных
    # 5. Проверить: count(ChromaDB) == count(Graph)
```
- **Ожидаемый результат:** Все 283+ chunks перенесены в граф
- **Проверка:** `curl -X POST http://localhost:8766/migrate` → `{"migrated": 283, "errors": 0}`

### Шаг 2.3: Интеграция с существующим IKKF
- [ ] Обновить `memory_system.py` → использовать Graph вместо ChromaDB
- [ ] Обновить `auto_save.py` → сохранять в Graph
- [ ] Обновить `kungfu_llm.py` → RAG через Graph
- [ ] Обновить `kungfu_skill.py` → поиск через Graph
- [ ] Оставить ChromaDB как read-only fallback
- **Ожидаемый результат:** Все модули работают с Graph
- **Проверка:** `curl http://localhost:8765/search?q=test` → результаты из графа

---

## Фаза 3: RAG через граф (2-3 дня)

### Шаг 3.1: GraphRAG класс
```python
class GraphRAG:
    def __init__(self, graph: KnowledgeGraph, llm: QwenLLM)
    
    def query(question: str, context_depth: int = 2) → str:
        # 1. Извлечь ключевые слова из вопроса
        # 2. Найти стартовые узлы (vector + keyword search)
        # 3. Расширить граф (BFS на context_depth)
        # 4. Ранжировать узлы по релевантности
        # 5. Сформировать контекст для LLM
        # 6. Отправить в LLM
        # 7. Проверить ответ (verify_answer)
        # 8. Сохранить Q&A как новые узлы
        # 9. Вернуть ответ
    
    def _extract_keywords(text) → list[str]
    def _find_seed_nodes(keywords, limit=5) → list[Node]
    def _expand_graph(seed_nodes, depth=2) → Subgraph
    def _rank_nodes(subgraph, question) → list[(Node, float)]
    def _format_context(nodes) → str
```
- **Ожидаемый результат:** RAG даёт точные ответы с контекстом из графа
- **Проверка:** `python3 -c "from graph.graph_rag import GraphRAG; rag = GraphRAG(...); print(rag.query('Что такое IKKF?'))"`

### Шаг 3.2: Оптимизация контекстного окна
- [ ] Реализовать приоритизацию узлов для входа в context window
- [ ] Реализовать суммаризацию дальних узлов
- [ ] Реализовать multi-hop reasoning (цепочки рассуждений)
- **Ожидаемый результат:** Эффективное использование context window LLM
- **Проверка:** Ответы на сложные вопросы с цепочками рассуждений

---

## Фаза 4: Тестирование и бенчмарки (1-2 дня)

### Шаг 4.1: Unit-тесты
```python
# tests/test_node.py
def test_node_creation()
def test_node_serialization()
def test_node_importance_update()

# tests/test_edge.py
def test_edge_creation()
def test_edge_strengthen()
def test_edge_bidirectional()

# tests/test_graph.py
def test_add_node()
def test_add_edge()
def test_bfs()
def test_dfs()
def test_find_path()
def test_vector_search()
def test_keyword_search()
def test_hybrid_search()

# tests/test_storage.py
def test_persistence()
def test_fts5_search()
def test_index_performance()

# tests/test_context.py
def test_context_encoding()
def test_context_similarity()
def test_context_extraction()

# tests/test_predictive.py
def test_prediction_accuracy()
def test_cache_hit_rate()
def test_lru_eviction()

# tests/test_consolidation.py
def test_duplicate_detection()
def test_node_merge()
def test_edge_discovery()
def test_importance_calculation()
```
- **Ожидаемый результат:** 50+ unit-тестов, все зелёные
- **Проверка:** `pytest tests/ -v` → 50 passed

### Шаг 4.2: Бенчмарк производительности
```python
# Сравнение: ChromaDB vs Graph
# Метрики: latency (p50, p95, p99), throughput (QPS), memory usage

# Тесты:
# 1. Поиск по 1K узлам
# 2. Поиск по 10K узлов
# 3. Поиск по 100K узлов
# 4. BFS depth=3 по 10K узлам
# 5. Path finding между случайными узлами
# 6. Запись 1000 узлов (throughput)
# 7. Мixed workload (80% read, 20% write)

# Ожидаемые результаты:
# - Поиск: <50ms для 10K узлов
# - BFS depth=3: <100ms для 10K узлов
# - Path finding: <200ms для 10K узлов
# - Запись: >500 nodes/sec
# - Memory: <50MB для 10K узлов (с LRU)
```
- **Ожидаемый результат:** Бенчмарк показывает улучшение vs ChromaDB
- **Проверка:** `python3 graph/benchmark.py` → отчёт с метриками

### Шаг 4.3: Интеграционное тестирование
- [ ] Полный цикл: запись → поиск → консолидация → поиск
- [ ] Миграция → проверка целостности → поиск
- [ ] RAG: вопрос → ответ → проверка точности
- [ ] API: все endpoints через curl
- **Ожидаемый результат:** Все интеграционные тесты проходят
- **Проверка:** `pytest tests/integration/ -v`

---

## Фаза 5: Развёртывание (1 день)

### Шаг 5.1: systemd unit для Graph API
```ini
[Unit]
Description=IKKF Graph API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/projects/i-know-kung-fu
ExecStartPre=/bin/bash -c 'fuser -k 8766/tcp 2>/dev/null; sleep 1'
ExecStart=/usr/local/lib/hermes-agent/venv/bin/python3 -m uvicorn graph.api:app --host 0.0.0.0 --port 8766
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
- **Ожидаемый результат:** Graph API запускается как сервис
- **Проверка:** `systemctl status ikkf-graph` → active (running)

### Шаг 5.2: Cron для консолидации
```cron
# Каждую ночь в 3:00 UTC
0 3 * * * cd /root/projects/i-know-kung-fu && /usr/local/lib/hermes-agent/venv/bin/python3 -c "from graph.consolidation import Consolidator; from graph.graph import KnowledgeGraph; g = KnowledgeGraph('data/graph.db'); c = Consolidator(g); c.run_full_cycle()" >> /var/log/ikkf-consolidation.log 2>&1
```
- **Ожидаемый результат:** Ночная консолидация запускается автоматически
- **Проверка:** `crontab -l` → запись есть

### Шаг 5.3: Мониторинг
- [ ] Health check endpoint: `GET /health`
- [ ] Stats endpoint: `GET /stats`
- [ ] Логирование в `/var/log/ikkf-graph.log`
- [ ] Алерт при падении (через systemd)
- **Ожидаемый результат:** Система мониторинга работает
- **Проверка:** `curl http://localhost:8766/health` → `{"status":"ok"}`

---

## Фаза 6: Документация (1 день)

### Шаг 6.1: Обновить TECHNICAL_SPEC.md
- [ ] Добавить раздел "Graph Knowledge Base"
- [ ] Обновить архитектурную диаграмму
- [ ] Добавить схему данных (ER-диаграмма)

### Шаг 6.2: Обновить ROADMAP.md
- [ ] Отметить Фазу 1 как в процессе
- [ ] Добавить подзадачи графового модуля

### Шаг 6.3: Создать README.md для GitHub
- [ ] Описание проекта
- [ ] Архитектура
- [ ] Quick start
- [ ] API reference
- [ ] Benchmarks

---

## Фаза 7: OWL Robot (отдельный поток)

### Шаг 7.1: Исследование библиотек
- [ ] Whisper для Ubuntu: `pip install faster-whisper`
- [ ] TTS: `pip install piper-tts` или `pip install TTS`
- [ ] Webcam: `pip install opencv-python`
- [ ] Проверить совместимость с MacBook i5

### Шаг 7.2: Базовый каркас
```python
class OWLRobot:
    def __init__(self):
        self.whisper = WhisperModel("tiny")
        self.tts = PiperTTS("ru_RU-irina-medium")
        self.webcam = cv2.VideoCapture(0)
        self.brain = GraphRAG(...)
    
    def listen() → str       # Слушать микрофон
    def speak(text)          # Говорить
    def see() → np.array     # Видеть через вебкамеру
    def think(question) → str  # Думать через GraphRAG
    def run()                # Главный цикл
```

### Шаг 7.3: Интеграция с сервером
- [ ] MacBook → сервер для тяжёлых задач
- [ ] Сервер → MacBook для обновлений графа
- [ ] Синхронизация через API

---

## Фаза 8: AI Affiliate Engine (отдельный поток)

### Шаг 8.1: Исследование ниш
- [ ] Выбрать 3-5 ниш для Telegram-каналов
- [ ] Найти партнёрские программы (CPA, CPL)
- [ ] Проверить легальность под РФ законодательство

### Шаг 8.2: Архитектура
```
affiliate/
├── channels/          # Управление Telegram-каналами
├── content/           # AI-генерация контenta
├── links/             # Управление партнёрскими ссылками
├── analytics/         # Аналитика и отчёты
└── monetization/      # Монетизация
```

### Шаг 8.3: MVP
- [ ] 1 Telegram-канал
- [ ] AI-генерация постов (Qwen 1.5B)
- [ ] Автопостинг через cron
- [ ] Трекинг кликов
- [ ] Партнёрские ссылки

---

## Таймлайн

| Фаза | Дни | Статус |
|------|-----|--------|
| 0: Подготовка | 1-2 | ⬜ |
| 1: Граф ядро | 3-5 | ⬜ |
| 2: API и интеграция | 2-3 | ⬜ |
| 3: RAG через граф | 2-3 | ⬜ |
| 4: Тестирование | 1-2 | ⬜ |
| 5: Развёртывание | 1 | ⬜ |
| 6: Документация | 1 | ⬜ |
| 7: OWL Robot | 5-7 | ⬜ |
| 8: Affiliate Engine | 5-7 | ⬜ |
| **Итого** | **21-31 день** | |

---

## Критерии готовности

- [ ] Graph хранит 10K+ узлов с связями
- [ ] Поиск <50ms для 10K узлов
- [ ] BFS depth=3 <100ms
- [ ] RAG даёт точные ответы на вопросы
- [ ] Миграция из ChromaDB прошла без потерь
- [ ] Ночная консолидация работает автоматически
- [ ] Все тесты зелёные (50+ unit, 10+ integration)
- [ ] API документирован
- [ ] Бенчмарк показывает улучшение vs ChromaDB

---

*План будет обновляться по мере продвижения.*
*Следующий шаг: Фаза 0, Шаг 0.1 — Очистка диска.*
