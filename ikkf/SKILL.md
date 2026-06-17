---
name: i-know-kung-fu
description: >
  IKKF Graph v2 — граф знаний для AI-агентов. Хранит всё важное в виде узлов и связей.
  Используй Graph API (порт 8766). Старый IKKF (8765) — мёртв, не используй.
  Автоматически сохраняй и ищи контекст.
---

# I Know Kung Fu — Граф знаний для Hermes

## Что это

IKKF — это **память** для AI-агента. Граф знаний: узлы (факты, концепты, события, действия, сущности) + связи (8 типов) + 5 контекстуальных измерений.

**API:** `http://127.0.0.1:8766` (FastAPI, systemd: `ikkf-graph.service`)

## Правила использования (ЖЁСТКИЕ)

### 1. ПЕРЕД ответом на вопрос — ВСЕГДА искать в IKKF

**Это обязательно.** Даже если кажется что знаешь ответ — сначала провери базу.

```bash
# Основной способ — через ikkf_tool.py:
python3 /root/projects/i-know-kung-fu/graph/ikkf_tool.py search "КЛЮЧЕВЫЕ СЛОВА" 5

# Если tool недоступен — через curl:
curl -s "http://127.0.0.1:8766/search/hybrid?q=ЗАПРОС&limit=5"
```

**Алгоритм:**
1. Извлеки ключевые слова из вопроса
2. Выполни `ikkf_tool.py search "ключевые слова"`
3. Если результат не "NO_RESULTS" → используй как контекст, цитируй дословно
4. Если NO_RESULTS → попробуй RAG
5. Если всё ещё 0 → используй session_search как fallback
6. Если в базе нет ответа → скажи честно "в базе нет данных"

### 2. ПОСЛЕ ответа — сохраняй важное

```bash
# Сохранить факт:
python3 /root/projects/i-know-kung-fu/graph/ikkf_tool.py store "ФАКТ" fact 0.8

# Извлечь факты из текста и сохранить:
python3 /root/projects/i-know-kung-fu/graph/ikkf_tool.py extract "Текст для анализа"
```

Не сохраняй всё подряд — только значимое: решения, факты о проектах, настройки, выводы.

Если в разговоре появилась новая информация (факт, решение, деталь проекта) — сохрани:

```python
def ikkf_store(content, node_type="fact", importance=0.5, tags=None, project="default"):
    """Сохранить в IKKF Graph."""
    url = 'http://127.0.0.1:8766/node'
    data = json.dumps({
        "content": content,
        "node_type": node_type,
        "importance": importance,
        "tags": tags or [],
        "project": project,
        "context": {"semantic": project}
    }).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())
```

### 3. Когда использовать что

| Ситуация | Действие |
|----------|----------|
| Вопрос пользователя | `ikkf_search()` → если есть результаты → цитируй |
| Новая информация | `ikkf_store()` в конце ответа |
| Нужен контекст узла | `GET /context/{node_id}?depth=2` |
| Нужен RAG | `POST /rag` с `{"query": "..."}` |
| Парсинг текста | `POST /parse` с `{"text": "..."}` |

### 4. Анти-галлюцинация

- Если `ikkf_search()` вернул результат → **цитируй дословно**, не пересказывай
- Если результата нет → скажи "в базе IKKF нет данных по X"
- **Никогда** не выдумывай факты от имени IKKF

## API Reference

### Быстрые вызовы (curl)

```bash
# Поиск
curl -s "http://127.0.0.1:8766/search?q=IKKF&search_type=hybrid&limit=5"

# Сохранить узел
curl -s -X POST http://127.0.0.1:8766/node \
  -H "Content-Type: application/json" \
  -d '{"content": "...", "node_type": "fact", "importance": 0.8, "project": "default"}'

# RAG запрос
curl -s -X POST http://127.0.0.1:8766/rag \
  -H "Content-Type: application/json" \
  -d '{"query": "Что такое IKKF?", "max_nodes": 5}'

# Контекст по тексту
curl -s "http://127.0.0.1:8766/context?q=IKKF&depth=2"

# Статистика
curl -s http://127.0.0.1:8766/stats
```

### Все эндпоинты

```
GET    /health               — проверка
GET    /stats                — статистика

POST   /node                 — создать узел
GET    /node/{id}            — получить узел
GET    /nodes                — список ( ?, type, project)
PUT    /node/{id}            — обновить
DELETE /node/{id}            — удалить

POST   /edge                 — создать связь
GET    /neighbors/{id}       — соседи узла
GET    /path/{from}/{to}      — путь между узлами

GET    /search?q=            — поиск (text/vector/hybrid)
GET    /context?q=           — контекст по тексту
GET    /context/{id}         — контекст узла
GET    /predict/{id}         — предсказание (2 хопа)

POST   /rag                  — RAG запрос
POST   /parse                — парсинг текста через LLM
POST   /fill-context         — заполнение spatial/emotional/social

GET    /projects             — проекты
GET    /documents            — документы
GET    /chunks               — чанки

POST   /consolidate          — запустить консолидацию
```

## Структура данных

### Типы узлов (6)

| Тип | Что | Пример |
|-----|-----|--------|
| fact | Факт, утверждение | "IKKF использует SQLite" |
| entity | Человек, проект, инструмент | "User", "Laptop" |
| action | Что было сделано | "Установил Ubuntu" |
| concept | Идея, определение | "Граф знаний — это..." |
| event | Событие | "Сообщение от 08.06" |
| project | Контейнер | "project_deepseek" |

### Типы связей (8)

| Тип | Что |
|-----|-----|
| semantic | Семантическая связь |
| temporal | Временная (до/после) |
| causal | Причинно-следственная |
| associative | Ассоциативная (общий контекст) |
| hierarchical | Иерархический (родитель/потомок) |
| contextual | Контекстуальный (тот же контекст) |
| similarity | Похожесть |
| sequence | Последовательность |

### 5 контекстуальных измерений

| Измерение | Что | Пример |
|-----------|-----|--------|
| temporal | Когда? | "2026-06" |
| spatial | Где? | "сервер", "MacBook" |
| semantic | О чём? | "разработка", "IKKF" |
| emotional | Тон? | "positive", "negative" |
| social | Кто? | "User", "AI" |

## Наблюдаемость (без веб-UI)

### Debug поиск
```bash
# Показать весь путь поиска:
python3 /root/projects/i-know-kung-fu/graph/ikkf_debug.py search "запрос"

# Показать GraphRAG пайплайн:
python3 /root/projects/i-know-kung-fu/graph/ikkf_debug.py rag "запрос"

# Статистика графа:
python3 /root/projects/i-know-kung-fu/graph/ikkf_debug.py stats

# Детали узла:
python3 /root/projects/i-know-kung-fu/graph/ikkf_debug.py node <node_id>

# Последний лог консолидации:
python3 /root/projects/i-know-kung-fu/graph/ikkf_debug.py consolidate-log
```

### Debug через API
```bash
# Hybrid search с debug:
curl -s "http://127.0.0.1:8766/search/hybrid?q=запрос&debug=true"

# RAG с debug (возвращает context_nodes):
curl -s -X POST http://127.0.0.1:8766/rag -H 'Content-Type: application/json' \
  -d '{"query":"запрос","debug":true}'
```

## Важно

- **Порт 8765 (старый IKKF) — МЁРТВ, не используй**
- **Порт 8766 — единственный рабочий**
- **Всегда используй hybrid поиск** для лучших результатов
- **Никогда не выдумывай** — если в базе нет данных, скажи честно
