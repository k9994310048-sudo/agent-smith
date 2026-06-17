# I Know Kung Fu (IKKF) — Граф знаний для AI-агентов

> Память для искусственного интеллекта. Хранит знания в виде графа: узлы + связи.

## Что это

IKKF — это **графовая база знаний** для AI-агентов (Hermes, OWL, и других).

Вместо плоского хранилища чанков текста использует **граф**:
- **Узлы** (Node) — факты, концепции, события, действия, сущности
- **Связи** (Edge) — 8 типов: семантическая, временная, причинная, ассоциативная, и др.
- **Контекст** — 5 измерений: временное, пространственное, семантическое, эмоциональное, социальное

### Зачем

- **Обычный RAG**: поиск похожих чанков → плоский список
- **IKKF**: поиск связанных узлов → расширение через граф → контекст с глубиной

Результат: AI понимает **связи** между фактами, а не просто находит похожие тексты.

## Архитектура

```
┌─────────────────────────────────────────────────┐
│                  HERMES / OWL                    │
│                                                  │
│  1. Поиск контекста → Graph API (порт 8766)     │
│  2. Сохранение новых данных → Graph API          │
└─────────────────────────────────────────────────┘
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
    ┌──────────┐ ┌─────────┐ ┌─────────┐
    │  Graph   │ │  RAG    │ │Predict- │
    │  Engine  │ │ Engine  │ │ ive     │
    └────┬─────┘ └────┬────┘ └────┬────┘
         │            │           │
         ▼            │           │
    ┌─────────┐       │           │
    │ SQLite  │       │           │
    │ (L2)    │       │           │
    └─────────┘       │           │
         ▲            │           │
         │      ┌─────┴─────┐     │
         │      │  LLM      │     │
         │      │ Qwen 0.5B │     │
         │      └───────────┘     │
         │                        │
    ┌────┴────────────────────────┴────┐
    │        L1: RAM Cache             │
    │   (горячие узлы, до 1000)        │
    └─────────────────────────────────┘
```

## Quick Start

### Установка

```bash
# 1. Клонировать
git clone <repo-url> ikkf
cd ikkf

# 2. Зависимости
pip install fastapi uvicorn llama-cpp-python

# 3. Модель (опционально, для LLM-парсинга)
bash scripts/download_model.sh

# 4. Запуск
python3 -m graph.api
```

### Использование

```bash
# Health check
curl http://127.0.0.1:8766/health

# Создать узел
curl -X POST http://127.0.0.1:8766/node \
  -H "Content-Type: application/json" \
  -d '{
    "content": "User installed Ubuntu 24.04 on MacBook",
    "node_type": "action",
    "importance": 0.8,
    "tags": ["ubuntu", "macBook"]
  }'

# Поиск
curl "http://127.0.0.1:8766/search?q=Ubuntu&search_type=hybrid&limit=5"

# Миграция из старого IKKF
python3 -m graph.migrate_to_graph
```

### Python API

```python
from graph.graph import Graph
from graph.graph_rag import GraphRAG

g = Graph()
rag = GraphRAG(g)

# Добавить узел
node = g.add_node("Важный факт", node_type="fact", importance=0.9)

# Добавить связь
g.add_edge(node1.id, node2.id, "semantic", 0.8)

# RAG запрос
result = rag.query("Что важного?")
print(result["context_text"])
```

## API Reference

| Метод | Endpoint | Описание |
|-------|----------|----------|
| `GET` | `/health` | Проверка работоспособности |
| `POST` | `/node` | Создать узел |
| `GET` | `/node/{id}` | Получить узел |
| `PUT` | `/node/{id}` | Обновить узел |
| `DELETE` | `/node/{id}` | Удалить узел |
| `GET` | `/nodes` | Список узлов (фильтры: type, project, status) |
| `POST` | `/edge` | Создать связь |
| `GET` | `/neighbors/{id}` | Соседи узла |
| `GET` | `/path/{from}/{to}` | Путь между узлами |
| `GET` | `/search` | Поиск (text / context / vector / hybrid) |
| `GET` | `/context/{id}` | Контекст для LLM |
| `GET` | `/predict/{id}` | Предсказать связанные |
| `POST` | `/consolidate` | Запустить консолидацию |
| `GET` | `/stats` | Статистика |

### Параметры поиска

- `q` — поисковый запрос
- `search_type` — `text` | `context` | `vector` | `hybrid`
- `project` — фильтр по проекту
- `limit` — количество результатов (max 100)

## Типы узлов

| Тип | Описание | Пример |
|-----|----------|--------|
| `fact` | Факт (утверждение) | "Земля круглая" |
| `concept` | Концепция (идея) | "Машинное обучение" |
| `action` | Действие | "User installed Ubuntu" |
| `entity` | Сущность | "User", "AI Agent" |
| `event` | Событие | "Запуск проекта" |
| `skill` | Нывык | "Как готовить пасту" |
| `project` | Проект | "IKKF" |
| `idea` | Идея | "Добавить видео" |

## Типы связей

| Тип | Описание |
|-----|----------|
| `semantic` | Семантическая (похож по смыслу) |
| `temporal` | Временная (до/после) |
| `causal` | Причинно-следственная |
| `associative` | Ассоциативная |
| `hierarchical` | Иерархическая (родитель/потомок) |
| `contextual` | Контекстуальная |
| `similarity` | Похожесть (векторная близость) |
| `sequence` | Последовательность |

## Бенчмарки

Сервер: 2 CPU, 3.8GB RAM, SSD

| Операция | Время |
|----------|-------|
| Create node | 1.57ms |
| Read node (кэш) | 0.003ms |
| Text search | 0.38ms |
| BFS (depth=5) | 0.10ms |
| Path finding | 0.08ms |
| RAG query | 6.34ms |
| Consolidation (171 узел) | 325ms |

## Структура проекта

```
ikkf/
├── graph/
│   ├── __init__.py        # Инициализация модуля
│   ├── node.py            # Node, Edge классы
│   ├── storage.py         # SQLite backend
│   ├── graph.py           # Основной граф
│   ├── api.py             # FastAPI сервер
│   ├── graph_rag.py       # RAG через граф
│   ├── kungfu_llm.py      # Qwen 0.5B для парсинга
│   ├── consolidation.py   # Ночная консолидация
│   ├── predictive.py      # Предиктивная подгрузка
│   ├── integration.py     # Интеграция со старым IKKF
│   ├── benchmark.py       # Бенчмарки
│   ├── migrate_to_graph.py # Миграция данных
│   ├── SKILL.md           # Инструкция для Hermes
│   └── ikkf-graph.service # systemd юнит
├── models/
│   └── Qwen2.5-0.5B-Instruct-Q4_K_M.gguf
└── data/
    └── graph.db           # SQLite БД
```

## Лицензия

MIT
