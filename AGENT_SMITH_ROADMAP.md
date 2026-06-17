# Agent Smith — Итоговый проект и Дорожная карта доработки

> **Автор:** Klim Bydancev  
> **Разработчик:** OWL (ZOO company)  
> **Дата:** 14 июня 2026  
> **Статус:** Базовый агент работает (минимальная форма)

---

## Содержание

1. [Резюме текущего состояния](#1-резюме-текущего-состояния)
2. [Архитектура системы](#2-архитектура-системы)
3. [Анализ текущей реализации](#3-анализ-текущей-реализации)
4. [Дорожная карта](#4-дорожная-карта)
5. [Детальный план по фазам](#5-детальный-план-по-фазам)
6. [Реальные инструменты и технологии](#6-реальные-инструменты-и-технологии)
7. [Интеграция с внешними API](#7-интеграция-с-внешними-api)
8. [Оценка трудозатрат](#8-оценка-трудозатрат)
9. [Риски и митигация](#9-риски-и-митигация)

---

## 1. Резюме текущего состояния

### Что уже работает

| Компонент | Статус | Описание |
|-----------|--------|----------|
| **Agent Smith (базовый)** | ✅ Работает | Цикл Perceive→Reason→Act→Learn через `agents/smith.py` |
| **LLM Provider** | ✅ Работает | Локальная Qwen2.5-1.5B (llama.cpp) + внешний API (OpenRouter) |
| **Telegram Bot** | ✅ Работает | Приём/отправка сообщений, команды `/api` |
| **Память (JSON)** | ✅ Работает | Факты, сны, идеи, история разговоров |
| **IKKF Bridge** | ✅ Работает | REST-клиент к Graph API (порт 8766) |
| **Извлечение фактов** | ✅ Работает | Regex-паттерны для извлечения фактов из диалога |
| **Когнитивная петля** | ✅ Работает | Сны → идеи (через `--dream`) |
| **IKKF Graph API** | ✅ Работает | FastAPI сервер, ChromaDB + SQLite FTS5 + sqlite-vec |
| **RAG Pipeline** | ✅ Работает | Гибридный поиск (BM25 + vector), контекстуализация |
| **IKKF_SH (базовый)** | ⚠️ Частично | Модули созданы, но интеграция с основным агентом неполная |

### Что НЕ работает / не интегрировано

| Компонент | Статус | Проблема |
|-----------|--------|----------|
| **Tool Calling / Function Calling** | ❌ Отсутствует | Агент не может вызывать внешние инструменты |
| **MCP (Model Context Protocol)** | ❌ Отсутствует | Нет стандартизированного подключения внешних API |
| **A2A (Agent-to-Agent)** | ❌ Отсутствует | Мультиагентная координация не реализована |
| **Self-Replication** | ❌ Отсутствует | Код есть в IKKF_SH, но не интегрирован |
| **Reasoning Engine** | ⚠️ Заготовка | Chain-of-thought есть, но не используется основным агентом |
| **Action Planner** | ⚠️ Заготовка | Планировщик создан, но не подключён к LLM |
| **Skill System** | ⚠️ Заготовка | Базовая структура есть, навыки не эволюционируют |
| **Deep Search** | ⚠️ Заготовка | arXiv/GitHub интеграция в IKKF_SH, не в основном агенте |
| **Verification** | ⚠️ Заготовка | Fact-checking модуль создан, не используется |
| **Web UI** | ✅ Работает | Базовый веб-интерфейс на порту 8767 |

---

## 2. Архитектура системы

### 2.1 Текущая архитектура (v0.1)

```
┌─────────────────────────────────────────────────────────┐
│                    Telegram Bot                         │
│              (integrations/telegram.py)                 │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP long-polling
                       ▼
┌─────────────────────────────────────────────────────────┐
│                   Agent Smith                           │
│              (agents/smith.py)                          │
│                                                         │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐           │
│  │  Perceive  │→│  Reason   │→│    Act    │           │
│  └───────────┘  └───────────┘  └───────────┘           │
│       ↑                              │                  │
│       └──────────────┬───────────────┘                  │
│                      ▼                                  │
│               ┌───────────┐                             │
│               │   Learn   │                             │
│               └───────────┘                             │
└───────┬────────────────────┬────────────────────────────┘
        │                    │
        ▼                    ▼
┌──────────────┐    ┌──────────────────┐
│ LLM Provider │    │  IKKF Graph API  │
│ (local/API)  │    │  (порт 8766)     │
└──────────────┘    └──────────────────┘
```

### 2.2 Целевая архитектура (v1.0)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Входные каналы                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ Telegram  │  │  Web UI  │  │ REST API │  │ CLI      │           │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘  └─────┬────┘           │
│        └──────────────┴──────────────┴──────────────┘               │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────┐
│                        Core Agent Loop                              │
│                                                                     │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐       │
│  │  Perceive  │→│  Reason   │→│   Plan    │→│    Act    │       │
│  │            │  │ (CoT+VC) │  │(Decomp)  │  │(ToolCall) │       │
│  └───────────┘  └───────────┘  └───────────┘  └─────┬─────┘       │
│       ↑                                              │              │
│       └──────────────────────┬───────────────────────┘              │
│                              ▼                                      │
│                     ┌───────────┐                                   │
│                     │   Learn   │                                   │
│                     │ (Reflect) │                                   │
│                     └───────────┘                                   │
└──────────┬──────────────────┬──────────────────┬────────────────────┘
           │                  │                  │
           ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  LLM Router  │  │   Tool Registry  │  │  Memory System   │
│              │  │                  │  │                  │
│ • Local Qwen │  │ • MCP Servers    │  │ • Working Memory │
│ • API (GPT)  │  │ • Built-in Tools │  │ • IKKF Graph     │
│ • Claude     │  │ • Custom Skills  │  │ • Long-term JSON │
│ • Ollama     │  │ • A2A Agents     │  │ • Semantic Search │
└──────────────┘  └──────────────────┘  └──────────────────┘
```

---

## 3. Анализ текущей реализации

### 3.1 Сильные стороны

1. **Рабочий базовый цикл** — Perceive→Reason→Act→Learn реализован и функционирует
2. **Гибридная LLM** — переключение между локальной моделью и внешним API
3. **IKKF Graph** — полноценная графовая память с RAG, гибридным поиском, векторами
4. **Когнитивная петля** — сны, идеи, ранжирование, воронка DCT
5. **Автосохранение** — каждый диалог сохраняется автоматически
6. **Автозапись правил** — агент учится на коррекциях пользователя
7. **Простая установка** — `python3 main.py` с интерактивной настройкой

### 3.2 Слабые стороны (для доработки)

1. **Нет tool calling** — агент не может вызывать внешние инструменты (curl, web search, файловые операции)
2. **Нет стандартизированного протокола** — каждый внешний API подключается вручную
3. **Нет streaming** — ответы генерируются целиком, без потоковой передачи
4. **Regex-извлечение фактов** — примитивное, нужен LLM-based extraction
5. **Нет multi-agent** — код есть, но не интегрирован
6. **Нет верификации** — агент не проверяет свои ответы
7. **Маленький контекст** — N_CTX = 2048 токенов для локальной модели

---

## 4. Дорожная карта

### Обзор фаз

```
2026 Q2-Q3: Фаза 1 — Tool Calling + MCP         [4-6 недель]
2026 Q3:    Фаза 2 — Умный Reasoning + Planning  [3-4 недели]
2026 Q3-Q4: Фаза 3 — Multi-Agent + A2A           [4-6 недель]
2026 Q4:    Фаза 4 — Advanced Memory + RAG v2     [3-4 недели]
2027 Q1:    Фаза 5 — Autonomy + Web Dashboard     [4-6 недель]
2027 Q1-Q2: Фаза 6 — Marketplace + Distribution   [6-8 недель]
```

```
Фаза 1          Фаза 2          Фаза 3          Фаза 4          Фаза 5          Фаза 6
Tool Calling    Reasoning       Multi-Agent     Memory v2       Autonomy        Marketplace
   │               │               │               │               │               │
   ▼               ▼               ▼               ▼               ▼               ▼
┌──────┐      ┌──────┐       ┌──────┐       ┌──────┐       ┌──────┐       ┌──────┐
│MCP   │      │CoT   │       │A2A   │       │Graph │       │Cron  │       │Docker│
│Tools │      │Plan  │       │Clones│       │RAG v2│       │WebUI │       │pip   │
│Skills│      │Verify│       │Orch. │       │Embed │       │API   │       │Skill │
└──────┘      └──────┘       └──────┘       └──────┘       └──────┘       └──────┘
```

---

## 5. Детальный план по фазам

### ФАЗА 1: Tool Calling + MCP (4-6 недель) 🔧

**Цель:** Агент получает способность вызывать внешние инструменты и подключать MCP-серверы.

#### 1.1 Базовый Tool Calling

**Что делаем:**
- Реализуем `tool_registry.py` — реестр доступных инструментов
- Реализуем `tool_executor.py` — выполнение вызовов инструментов
- Добавляем поддержку function calling в `llm_provider.py`
- Создаём базовые встроенные инструменты

**Реальные инструменты:**

| Инструмент | Реализация | Описание |
|-----------|-----------|----------|
| `shell_exec` | `subprocess.run()` | Выполнение shell-команд |
| `web_search` | DuckDuckGo API / SearXNG | Поиск в интернете |
| `web_fetch` | `urllib` + `BeautifulSoup` | Извлечение контента с URL |
| `file_read` | `open()` | Чтение файлов |
| `file_write` | `open()` | Запись файлов |
| `python_exec` | `exec()` / `subprocess` | Выполнение Python-кода |
| `ikkf_search` | IKKF Bridge | Поиск в графе знаний |
| `ikkf_store` | IKKF Bridge | Сохранение в граф |
| `telegram_send` | Telegram Bot API | Отправка сообщений |

**Архитектура Tool Calling:**

```python
# tool_registry.py
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema
    handler: Callable

class ToolRegistry:
    tools: Dict[str, Tool]
    
    def register(self, tool: Tool): ...
    def get_schemas(self) -> list: ...  # Для промпта LLM
    def execute(self, name: str, params: dict) -> str: ...

# tool_executor.py
class ToolExecutor:
    def __init__(self, registry: ToolRegistry, llm: LLMProvider): ...
    
    def run_with_tools(self, messages: list, max_iterations: int = 5) -> str:
        """Цикл: LLM → tool_call → execute → LLM → ..."""
        for _ in range(max_iterations):
            response = self.llm.generate(messages, tools=self.registry.get_schemas())
            if not response.has_tool_calls:
                return response.content
            for call in response.tool_calls:
                result = self.registry.execute(call.name, call.params)
                messages.append({"role": "tool", "content": result})
```

**Интеграция с LLM:**

Для OpenRouter API (совместимого с OpenAI):
```python
# Добавить поддержку tools в APIProvider
def generate(self, messages, tools=None, max_tokens=512):
    payload = {
        "model": self.model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools  # OpenAI function calling format
    # ... отправка запроса
```

Для локальной Qwen2.5-1.5B:
- Qwen2.5 поддерживает function calling через `llama-cpp-python`
- Формат: special tokens `<|tool_call|>` и `<|/tool_call|>`
- Альтернатива: prompt-based tool calling (менее надёжно)

#### 1.2 MCP (Model Context Protocol)

**Что это:** Стандартизированный протокол от Anthropic (ноябрь 2024) для подключения внешних инструментов к AI-агентам. Работает как "USB-C для AI".

**Как реализовать:**

| Компонент | Библиотека | Описание |
|-----------|-----------|----------|
| MCP Client | `mcp` (PyPI: `mcp`) | Официальный Python SDK |
| MCP Server | `mcp` | Создание собственных серверов |
| Транспорт | stdio / SSE / WebSocket | Способ связи клиента и сервера |

**Установка:**
```bash
pip install mcp
```

**Архитектура MCP в Agent Smith:**

```python
# mcp_manager.py
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class MCPManager:
    def __init__(self):
        self.sessions: Dict[str, ClientSession] = {}
        self.tools: Dict[str, dict] = {}
    
    async def connect_server(self, name: str, command: str, args: list):
        """Подключить MCP-сервер через stdio."""
        params = StdioServerParameters(command=command, args=args)
        read, write = await stdio_client(params).__aenter__()
        session = ClientSession(read, write)
        await session.__aenter__()
        await session.initialize()
        self.sessions[name] = session
        
        # Получаем список инструментов
        tools = await session.list_tools()
        for tool in tools.tools:
            self.tools[f"{name}:{tool.name}"] = {
                "server": name,
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema,
            }
    
    async def call_tool(self, full_name: str, arguments: dict) -> str:
        """Вызвать инструмент на MCP-сервере."""
        server_name, tool_name = full_name.split(":", 1)
        session = self.sessions[server_name]
        result = await session.call_tool(tool_name, arguments)
        return result.content[0].text
```

**Популярные MCP-серверы (реальные, доступные на GitHub):**

| MCP-сервер | Репозиторий | Возможности |
|-----------|-----------|------------|
| **filesystem** | `modelcontextprotocol/servers` | Чтение/запись файлов |
| **github** | `modelcontextprotocol/servers` | Репозитории, issues, PR |
| **postgres** | `modelcontextprotocol/servers` | Запросы к PostgreSQL |
| **brave-search** | `modelcontextprotocol/servers` | Поиск в интернете (Brave) |
| **puppeteer** | `modelcontextprotocol/servers` | Управление браузером |
| **memory** | `modelcontextprotocol/servers` | Долговременная память |
| **sequential-thinking** | `modelcontextprotocol/servers` | Пошаговое рассуждение |
| **sqlite** | `modelcontextprotocol/servers` | Работа с SQLite |
| **slack** | `modelcontextprotocol/servers` | Интеграция со Slack |
| **google-maps** | `modelcontextprotocol/servers` | Google Maps API |

**Пример конфигурации MCP:**

```json
// ~/.agent-smith/mcp_servers.json
{
  "servers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/mac"]
    },
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"],
      "env": {
        "BRAVE_API_KEY": "your-key-here"
      }
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "your-token"
      }
    },
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"]
    }
  }
}
```

#### 1.3 Улучшенная Skill System

```python
# skills/evolving_skill.py
class EvolvingSkill:
    """Навык, который эволюционирует через практику."""
    name: str
    content: str  # SKILL.md
    version: str
    success_count: int
    fail_count: int
    known_issues: List[dict]  # [{problem, solution, timestamp}]
    
    def on_success(self):
        self.success_count += 1
    
    def on_failure(self, error: str, context: dict):
        self.fail_count += 1
        self.known_issues.append({
            "problem": error,
            "solution": "",  # LLM сформулирует решение
            "timestamp": datetime.now().isoformat()
        })
        self.version = bump_version(self.version)
    
    @property
    def success_rate(self) -> float:
        total = self.success_count + self.fail_count
        return self.success_count / total if total > 0 else 0.5
```

**Deliverables Фазы 1:**
- [ ] `tool_registry.py` — реестр инструментов
- [ ] `tool_executor.py` — цикл выполнения tool calls
- [ ] `mcp_manager.py` — менеджер MCP-серверов
- [ ] Обновлённый `llm_provider.py` — поддержка function calling
- [ ] 9+ встроенных инструментов
- [ ] Конфигурация MCP-серверов
- [ ] Обновлённый `agents/smith.py` — интеграция tool calling

---

### ФАЗА 2: Умный Reasoning + Planning (3-4 недели) 🧠

**Цель:** Агент рассуждает пошагово, планирует действия и проверяет результаты.

#### 2.1 Reasoning Engine (Chain-of-Thought + Verification)

**Реальные подходы:**

| Подход | Описание | Примеры |
|--------|----------|---------|
| **Chain-of-Thought (CoT)** | Пошаговое рассуждение | "Давай думать шаг за шагом" |
| **Tree-of-Thought (ToT)** | Параллельные ветки рассуждений | Генерация нескольких вариантов |
| **Self-Consistency** | Многократный прогон + голосование | 5 раз сгенерировать, взять majority |
| **Reflection** | Агент проверяет собственный ответ | "Проверь свой ответ на ошибки" |
| **ReAct** | Чередование рассуждений и действий | Thought → Action → Observation → ... |

**Реализация ReAct (наиболее подходящая для Agent Smith):**

```python
# reasoning/react_engine.py
class ReActEngine:
    """Движок рассуждений ReAct (Reason + Act)."""
    
    REACT_PROMPT = """Ты — Agent Smith. Рассуждай пошагово.

Доступные инструменты:
{tools_description}

Задача: {task}

Формат (повторяй пока задача не решена):
Thought: [что думаю]
Action: [название_инструмента]
Action Input: {{"параметр": "значение"}}
... (после выполнения)
Observation: [результат]
... (повторяй)

Thought: [итоговый вывод]
Final Answer: [ответ]"""

    def __init__(self, llm, tool_registry):
        self.llm = llm
        self.tools = tool_registry
        self.max_steps = 10
    
    def solve(self, task: str) -> str:
        messages = [{"role": "user", "content": self.format_prompt(task)}]
        
        for step in range(self.max_steps):
            response = self.llm.generate(messages)
            
            # Парсим Thought / Action / Final Answer
            parsed = self.parse_react(response)
            
            if parsed.final_answer:
                return parsed.final_answer
            
            if parsed.action:
                # Выполняем инструмент
                result = self.tools.execute(parsed.action, parsed.action_input)
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": f"Observation: {result}"})
        
        return "Достигнут лимит шагов."
```

#### 2.2 Action Planner

```python
# planner/task_planner.py
class TaskPlanner:
    """Декомпозиция сложных задач на подзадачи."""
    
    def decompose(self, task: str, context: str) -> List[ActionStep]:
        """Разбить задачу на шаги."""
        prompt = f"""Разбей задачу на конкретные шаги с инструментами.

Задача: {task}
Контекст: {context}
Доступные инструменты: {self.tools_list}

Формат (JSON):
[
  {{"step": 1, "description": "...", "tool": "...", "params": {{}}, "depends_on": []}},
  {{"step": 2, "description": "...", "tool": "...", "params": {{}}, "depends_on": [1]}}
]"""
        
        response = self.llm.generate([{"role": "user", "content": prompt}])
        return json.loads(response)
    
    def execute_plan(self, plan: List[ActionStep]) -> List[dict]:
        """Выполнить план, учитывая зависимости."""
        results = {}
        for step in sorted(plan, key=lambda s: s.step):
            # Ждём завершения зависимостей
            deps_ok = all(results.get(d) is not None for d in step.depends_on)
            if not deps_ok:
                results[step.step] = {"error": "dependency failed"}
                continue
            
            # Выполняем шаг
            result = self.tools.execute(step.tool, step.params)
            results[step.step] = result
        return results
```

#### 2.3 Self-Reflection

```python
# reasoning/reflection.py
class SelfReflection:
    """Агент проверяет и улучшает собственный ответ."""
    
    REFLECT_PROMPT = """Проверь этот ответ на ошибки и неполноту.

Вопрос: {question}
Ответ: {answer}

Проверь:
1. Фактическая точность
2. Логическая непротиворечивость  
3. Полнота ответа
4. Практическая польза

Если нашёл ошибки — исправь и дай улучшенный ответ.
Если ответ правильный — подтверди."""

    def reflect(self, question: str, answer: str) -> str:
        messages = [{"role": "user", "content": self.REFLECT_PROMPT.format(
            question=question, answer=answer
        )}]
        return self.llm.generate(messages)
```

**Deliverables Фазы 2:**
- [ ] `reasoning/react_engine.py` — ReAct движок
- [ ] `reasoning/reflection.py` — Self-Reflection
- [ ] `planner/task_planner.py` — Декомпозиция задач
- [ ] Интеграция с Tool Calling из Фазы 1
- [ ] Обновлённый системный промпт

---

### ФАЗА 3: Multi-Agent + A2A (4-6 недель) 🤖🤖

**Цель:** Агент может клонировать себя и координировать работу нескольких агентов.

#### 3.1 A2A Protocol (Agent-to-Agent)

**Что это:** Протокол от Google (апрель 2025) для общения между AI-агентами от разных вендоров. Работает через HTTP с JSON-RPC 2.0.

**Ключевые концепции:**
- **Agent Card** — JSON-описание возможностей агента (как `robots.txt` для агентов)
- **Task** — Задача, передаваемая между агентами
- **Message/Artifact** — Сообщения и результаты внутри задачи

**Реализация:**

```python
# a2a/agent_card.py
class AgentCard:
    """Описание возможностей агента (A2A стандарт)."""
    name: str
    description: str
    url: str  # URL для связи с агентом
    version: str
    capabilities: dict  # {"streaming": True, "pushNotifications": False}
    skills: list  # [{"id": "...", "name": "...", "description": "..."}]
    
    def to_json(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "version": self.version,
            "capabilities": self.capabilities,
            "skills": self.skills,
        }

# a2a/task_manager.py
class A2ATaskManager:
    """Управление задачами A2A протокола."""
    
    def create_task(self, skill_id: str, message: str) -> dict:
        """Создать задачу для другого агента."""
        return {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": {
                "id": str(uuid.uuid4()),
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": message}]
                },
                "metadata": {"skillId": skill_id}
            }
        }
    
    def handle_task(self, request: dict) -> dict:
        """Обработать входящую задачу от другого агента."""
        task_id = request["params"]["id"]
        message = request["params"]["message"]["parts"][0]["text"]
        
        # Выполняем задачу
        result = self.agent.process_message(message)
        
        return {
            "jsonrpc": "2.0",
            "result": {
                "id": task_id,
                "status": {"state": "completed"},
                "artifacts": [{"parts": [{"type": "text", "text": result}]}]
            }
        }
```

#### 3.2 Self-Replication (Самокопирование)

```python
# agents/replication.py
class ReplicationEngine:
    """Движок самокопирования агентов."""
    
    def __init__(self, parent_agent):
        self.parent = parent_agent
        self.children: Dict[str, AgentSmith] = {}
    
    def replicate(self, count: int = 1, task: str = None) -> List[AgentSmith]:
        """Создать клонов агента."""
        clones = []
        for i in range(count):
            clone = AgentSmith(
                name=f"{self.parent.name}_clone_{i}",
                parent_id=self.parent.id,
            )
            clone.initialize()
            self.children[clone.id] = clone
            clones.append(clone)
            
            if task:
                clone.assign_task(task)
        
        return clones
    
    def aggregate_results(self, task_id: str) -> str:
        """Агрегировать результаты от клонов."""
        results = []
        for clone_id, clone in self.children.items():
            if clone.current_task_id == task_id:
                results.append(clone.get_result())
        
        # LLM агрегирует результаты
        prompt = f"Агрегируй результаты от {len(results)} агентов:\n"
        for i, r in enumerate(results):
            prompt += f"\n--- Агент {i+1} ---\n{r}"
        
        return self.parent.llm.generate([{"role": "user", "content": prompt}])
```

#### 3.3 Multi-Agent Orchestrator

```python
# agents/orchestrator.py
class MultiAgentOrchestrator:
    """Оркестратор мультиагентной системы."""
    
    def __init__(self, main_agent):
        self.main = main_agent
        self.workers: Dict[str, AgentSmith] = {}
        self.task_queue = asyncio.Queue()
    
    async def run_parallel_tasks(self, tasks: List[str]) -> List[str]:
        """Запустить задачи параллельно на клонах."""
        import asyncio
        
        # Создаём клонов
        engine = ReplicationEngine(self.main)
        clones = engine.replicate(count=len(tasks))
        
        # Запускаем параллельно
        async def run_task(clone, task):
            return clone.process_message(task)
        
        results = await asyncio.gather(*[
            run_task(clone, task) 
            for clone, task in zip(clones, tasks)
        ])
        
        return results
```

**Deliverables Фазы 3:**
- [ ] `a2a/agent_card.py` — Agent Card (A2A)
- [ ] `a2a/task_manager.py` — A2A Task Manager
- [ ] `a2a/server.py` — A2A HTTP Server (FastAPI)
- [ ] `agents/replication.py` — Self-Replication Engine
- [ ] `agents/orchestrator.py` — Multi-Agent Orchestrator
- [ ] HTTP API для A2A коммуникации

---

### ФАЗА 4: Advanced Memory + RAG v2 (3-4 недели) 💾

**Цель:** Улучшение системы памяти и RAG-пайплайна.

#### 4.1 Улучшенное извлечение фактов

**Текущее (regex):**
```python
patterns = [r"(?:Я|мой|моя)\s+([^.!?]{10,100})"]
```

**Новое (LLM-based):**
```python
class FactExtractor:
    """Извлечение фактов через LLM."""
    
    EXTRACT_PROMPT = """Извлек ключевые факты из этого диалога.
Верни JSON-массив фактов с типами и важностью.

Диалог:
{dialog}

Формат:
[
  {"content": "факт", "type": "fact|preference|event|decision", 
   "importance": 0.0-1.0, "tags": ["tag1"]}
]"""
    
    def extract(self, user_msg: str, assistant_msg: str) -> List[dict]:
        response = self.llm.generate([{
            "role": "user", 
            "content": self.EXTRACT_PROMPT.format(dialog=f"User: {user_msg}\nAssistant: {assistant_msg}")
        }])
        return json.loads(response)
```

#### 4.2 Memory Consolidation (Консолидация памяти)

```python
# memory/consolidation.py
class MemoryConsolidation:
    """Периодическая консолидация памяти."""
    
    def consolidate(self):
        """Объединить дублирующиеся факты, удалить устаревшие."""
        facts = self.ikkf.get_all_facts()
        
        # 1. Дедупликация (по семантическому сходству)
        clusters = self.cluster_similar(facts, threshold=0.85)
        for cluster in clusters:
            merged = self.merge_facts(cluster)
            self.ikkf.replace(cluster, merged)
        
        # 2. Забывание неважных фактов (importance decay)
        for fact in facts:
            age_days = (now - fact.created_at).days
            decay = math.exp(-0.01 * age_days)  # Экспоненциальное забывание
            effective_importance = fact.importance * decay
            if effective_importance < 0.1:
                self.ikkf.archive(fact)
        
        # 3. Генерация саммари для старых кластеров
        old_clusters = self.get_old_clusters(min_age_days=30)
        for cluster in old_clusters:
            summary = self.llm.summarize(cluster.facts)
            self.ikkf.store_summary(cluster, summary)
```

#### 4.3 Semantic Memory Graph

```python
# memory/semantic_graph.py
class SemanticMemoryGraph:
    """Расширенный граф памяти с семантическими связями."""
    
    def build_connections(self):
        """Автоматически связать релевантные узлы."""
        nodes = self.ikkf.get_all_nodes()
        for node in nodes:
            # Находим похожие узлы через embeddings
            similar = self.ikkf.vector_search(node.content, limit=5)
            for sim_node in similar:
                if sim_node.id != node.id:
                    # Определяем тип связи через LLM
                    relation = self.classify_relation(node, sim_node)
                    self.ikkf.add_edge(node.id, sim_node.id, relation)
```

**Deliverables Фазы 4:**
- [ ] `memory/fact_extractor.py` — LLM-based извлечение фактов
- [ ] `memory/consolidation.py` — Консолидация памяти
- [ ] `memory/semantic_graph.py` — Семантический граф
- [ ] `memory/forgetting.py` — Экспоненциальное забывание
- [ ] Cron-задача для периодической консолидации

---

### ФАЗА 5: Autonomy + Web Dashboard (4-6 недель) 🔄

**Цель:** Полная автономность агента и удобный веб-интерфейс.

#### 5.1 Автономный цикл

```python
# autonomy/scheduler.py
class AutonomousScheduler:
    """Планировщик автономных задач."""
    
    TASKS = [
        {"name": "dream_cycle", "cron": "0 6 * * *", "description": "Утренние сны"},
        {"name": "deep_search", "cron": "0 9 * * *", "description": "Глубокий поиск новостей"},
        {"name": "memory_consolidation", "cron": "0 3 * * 0", "description": "Консолидация памяти (еженедельно)"},
        {"name": "rule_capture", "cron": "*/30 * * * *", "description": "Запись правил из коррекций"},
        {"name": "auto_save", "cron": "*/15 * * * *", "description": "Автосохранение сообщений"},
        {"name": "health_check", "cron": "*/5 * * * *", "description": "Проверка здоровья системы"},
        {"name": "proactive_report", "cron": "0 20 * * *", "description": "Вечерний отчёт owner'у"},
    ]
    
    def run_task(self, task_name: str):
        """Выполнить автономную задачу."""
        if task_name == "dream_cycle":
            self.agent.dream()
            self.agent.generate_ideas()
        elif task_name == "deep_search":
            topics = self.get_relevant_topics()
            self.deep_search.search_and_store(topics)
        elif task_name == "proactive_report":
            report = self.generate_daily_report()
            self.telegram.send_message(report)
```

#### 5.2 Proactive Behavior (Проактивное поведение)

```python
# autonomy/proactive.py
class ProactiveAgent:
    """Агент, который действует проактивно."""
    
    def check_opportunities(self):
        """Проверить возможности для проактивных действий."""
        # 1. Новые идеи из снов → предложить реализацию
        ideas = self.ikkf.get_high_rated_ideas(min_score=0.7)
        for idea in ideas:
            self.telegram.send_message(
                f"💡 <b>Идея для реализации:</b>\n{idea.content}\n\n"
                f"Хочешь, чтобы я начал работу над этим?"
            )
        
        # 2. Изменения в проектах → отчёт
        changes = self.detect_project_changes()
        if changes:
            self.telegram.send_message(
                f"📊 <b>Обнаружены изменения:</b>\n{changes}"
            )
        
        # 3. Напоминания из памяти
        reminders = self.check_reminders()
        for reminder in reminders:
            self.telegram.send_message(f"⏰ <b>Напоминание:</b> {reminder}")
```

#### 5.3 Web Dashboard

```python
# web/dashboard.py
"""Веб-интерфейс Agent Smith на FastAPI + HTMX."""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Agent Smith Dashboard")

@app.get("/")
async def dashboard(request: Request):
    """Главная страница дашборда."""
    return templates.TemplateResponse("dashboard.html", {
        "agent_status": agent.get_status(),
        "recent_conversations": agent.memory["conversations"][-20:],
        "facts_count": len(agent.memory["facts"]),
        "dreams_count": len(agent.memory["dreams"]),
        "ideas_count": len(agent.memory["ideas"]),
        "ikkf_stats": agent.ikkf.stats() if agent.ikkf else {},
    })

@app.post("/api/chat")
async def api_chat(message: str):
    """REST API для чата с агентом."""
    response = agent.process_message(message)
    return {"response": response}

@app.get("/api/status")
async def api_status():
    """API статуса агента."""
    return agent.get_status()

@app.get("/api/memory")
async def api_memory():
    """API памяти агента."""
    return agent.memory

@app.get("/api/ikkf/stats")
async def api_ikkf_stats():
    """API статистики IKKF."""
    return agent.ikkf.stats() if agent.ikkf else {}
```

**Deliverables Фазы 5:**
- [ ] `autonomy/scheduler.py` — Планировщик автономных задач
- [ ] `autonomy/proactive.py` — Проактивное поведение
- [ ] `web/dashboard.py` — Веб-дашборд (FastAPI + HTMX)
- [ ] `web/templates/` — HTML шаблоны
- [ ] Systemd сервисы для автономного запуска
- [ ] Cron-задачи для периодических задач

---

### ФАЗА 6: Marketplace + Distribution (6-8 недель) 📦

**Цель:** Распространение Agent Smith как продукта.

#### 6.1 Docker-образ

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода
COPY . .

# Модели (или скачать при сборке)
RUN mkdir -p models/qwen2.5-1.5b

EXPOSE 8766 8767

CMD ["python3", "main.py"]
```

```yaml
# docker-compose.yml
version: '3.8'
services:
  agent-smith:
    build: .
    ports:
      - "8766:8766"  # IKKF API
      - "8767:8767"  # Web UI
    volumes:
      - agent-data:/root/.agent-smith
      - ikkf-data:/app/i-know-kung-fu/graph/data
    environment:
      - TELEGRAM_TOKEN=${TELEGRAM_TOKEN}
      - API_KEY=${API_KEY}
    restart: unless-stopped

volumes:
  agent-data:
  ikkf-data:
```

#### 6.2 Skill Marketplace

```python
# marketplace/skill_store.py
class SkillStore:
    """Магазин навыков для Agent Smith."""
    
    def __init__(self, registry_url: str = "https://skills.agent-smith.dev"):
        self.registry = registry_url
    
    def search(self, query: str) -> List[dict]:
        """Найти навык в маркетплейсе."""
        # HTTP запрос к реестру
        ...
    
    def install(self, skill_id: str):
        """Установить навык из маркетплейса."""
        skill_data = self.download(skill_id)
        self.local_registry.register(skill_data)
    
    def publish(self, skill: EvolvingSkill):
        """Опубликовать навык в маркетплейсе."""
        # HTTP POST к реестру
        ...
```

#### 6.3 pip-пакет

```python
# setup.py
from setuptools import setup, find_packages

setup(
    name="agent-smith",
    version="1.0.0",
    description="Autonomous AI Agent with infinite memory",
    author="Klim Bydancev",
    packages=find_packages(),
    install_requires=[
        "fastapi",
        "uvicorn",
        "llama-cpp-python",
        "mcp",
        "chromadb",
        "aiosqlite",
    ],
    entry_points={
        "console_scripts": [
            "agent-smith=main:main",
        ],
    },
)
```

**Deliverables Фазы 6:**
- [ ] `Dockerfile` + `docker-compose.yml`
- [ ] `setup.py` / `pyproject.toml` для pip
- [ ] Skill Marketplace (реестр навыков)
- [ ] Документация для разработчиков
- [ ] Примеры MCP-серверов для Agent Smith
- [ ] README с инструкциями по установке

---

## 6. Реальные инструменты и технологии

### 6.1 LLM для автономного агента

| Модель | Параметры | Контекст | Подходит для | Ссылка |
|--------|-----------|----------|-------------|--------|
| **Qwen2.5-1.5B** | 1.5B | 32K | Локально, слабые устройства | huggingface.co/Qwen/Qwen2.5-1.5B-Instruct |
| **Qwen2.5-7B** | 7B | 128K | Локально (8GB RAM), основная модель | huggingface.co/Qwen/Qwen2.5-7B-Instruct |
| **Qwen2.5-14B** | 14B | 128K | Локально (16GB RAM), продвинутые задачи | huggingface.co/Qwen/Qwen2.5-14B-Instruct |
| **Llama 3.1-8B** | 8B | 128K | Локально, good balance | huggingface.co/meta-llama/Llama-3.1-8B-Instruct |
| **Mistral Small 3.1** | 24B | 128K | Локально (GPU), отличный | huggingface.co/mistralai/Mistral-Small-3.1-24B-Instruct |
| **Phi-4** | 14B | 16K | Локально, Microsoft | huggingface.co/microsoft/phi-4 |
| **Gemma 3** | 4B-27B | 128K | Локально, Google | huggingface.co/google/gemma-3 |
| **DeepSeek-V3** | 671B (MoE) | 128K | API, топ-качество | api.deepseek.com |
| **Claude 3.5 Sonnet** | — | 200K | API, лучший для агентов | api.anthropic.com |
| **GPT-4o** | — | 128K | API, универсальный | api.openai.com |

**Рекомендация для Agent Smith:**
- **Локально:** Qwen2.5-7B-Instruct Q4_K_M (≈4.5GB, работает на 8GB RAM)
- **API (основной):** DeepSeek-V3 или Claude 3.5 Sonnet
- **API (бесплатный):** OpenRouter free tier (текущий подход)
- **Fallback:** Qwen2.5-1.5B (текущая модель, для слабых устройств)

### 6.2 Frameworks для AI-агентов

| Framework | Описание | Язык | Подходит для Agent Smith? |
|-----------|----------|------|--------------------------|
| **LangGraph** | Stateful agent workflows от LangChain | Python | ⚠️ Переусложнён для текущей архитектуры |
| **CrewAI** | Multi-agent orchestration | Python | ✅ Хорош для Phase 3 |
| **AutoGen** | Microsoft multi-agent framework | Python | ✅ Хорош для Phase 3 |
| **Semantic Kernel** | Microsoft AI orchestration | Python/C# | ⚠️ Избыточно |
| **Haystack** | RAG pipeline framework | Python | ✅ Хорош для Phase 4 |
| **DSPy** | Programming (not prompting) LM | Python | ✅ Интересен для reasoning |
| **Phidata** | Agent toolkit with tools | Python | ✅ Хорош для Phase 1 |
| **PydanticAI** | Type-safe AI agents | Python | ✅ Современный подход |
| **OpenAI Agents SDK** | Official OpenAI agent framework | Python | ⚠️ Привязка к OpenAI |
| **Anthropic Tool Use** | Claude tool calling | Python | ✅ Нативная поддержка tools |
| **MCP SDK** | Model Context Protocol | Python/TS | ✅ Ключевой для Phase 1 |

**Ключевой инсайт:** Agent Smith уже имеет свою архитектуру. Не нужно移植 entire framework — лучше интегрировать лучшие идеи и протоколы (MCP, A2A) в существующую систему.

### 6.3 Протоколы для внешних API

| Протокол | Автор | Год | Назначение | Статус |
|----------|-------|-----|-----------|--------|
| **MCP (Model Context Protocol)** | Anthropic | 2024 | Подключение инструментов к LLM | ✅ Стандарт, 1000+ серверов |
| **A2A (Agent-to-Agent Protocol)** | Google | 2025 | Общение между AI-агентами | ✅ Стандарт, растущее сообщество |
| **Function Calling (OpenAI)** | OpenAI | 2023 | Вызов функций из LLM | ✅ Де-факто стандарт |
| **Tool Use (Anthropic)** | Anthropic | 2023 | Вызов инструментов Claude | ✅ Работает |
| **Responses API** | OpenAI | 2025 | Новый API для агентов | ✅ Новый, перспективный |

### 6.4 Хранилища данных

| Технология | Назначение | Используется? |
|-----------|-----------|---------------|
| **ChromaDB** | Векторная БД | ✅ Уже в IKKF |
| **SQLite + FTS5** | Полнотекстовый поиск | ✅ Уже в IKKF |
| **sqlite-vec** | Векторный поиск в SQLite | ✅ Уже в IKKF |
| **Qdrant** | Векторная БД (prod) | ❌ Альтернатива ChromaDB |
| **Milvus** | Векторная БД (масштаб) | ❌ Для масштабирования |
| **Redis** | Кэш + pub/sub | ❌ Для real-time |
| **Neo4j** | Графовая БД | ❌ Альтернатива IKKF Graph |
| **Apache AGE** | Графовые расширения PostgreSQL | ❌ Для PostgreSQL |

### 6.5 Инструменты для веб-поиска

| Инструмент | API | Бесплатный лимит | Качество |
|-----------|-----|-------------------|----------|
| **DuckDuckGo** | `duckduckgo-search` (PyPI) | Неограниченно | Среднее |
| **SearXNG** | Self-hosted | Неограниченно | Хорошее |
| **Brave Search** | REST API | 2000 запросов/мес | Хорошее |
| **Tavily** | REST API | 1000 запросов/мес | Отличное (для AI) |
| **Google Custom Search** | REST API | 100 запросов/день | Отличное |
| **SerpAPI** | REST API | 100 запросов/мес | Отличное |
| **Exa.ai** | REST API | Бесплатный tier | Отличное (neural) |
| **Jina AI Reader** | REST API | 1000 запросов/мес | Хорошее (для парсинга) |

**Рекомендация:** `duckduckgo-search` (PyPI) для базового поиска + Tavily для AI-оптимизированного поиска.

---

## 7. Интеграция с внешними API

### 7.1 Текущая поддержка

```
✅ OpenRouter API (LLM)
✅ Telegram Bot API (мессенджер)
✅ IKKF Graph API (память)
```

### 7.2 План подключения внешних API

#### Приоритет 1 (Фаза 1): Базовые инструменты

```python
# tools/web_search.py
class WebSearchTool:
    """Поиск в интернете через DuckDuckGo."""
    name = "web_search"
    description = "Поиск информации в интернете"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Поисковый запрос"},
            "max_results": {"type": "integer", "default": 5}
        },
        "required": ["query"]
    }
    
    def execute(self, query: str, max_results: int = 5) -> str:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return json.dumps(results, ensure_ascii=False)

# tools/shell_exec.py
class ShellExecTool:
    """Выполнение shell-команд."""
    name = "shell_exec"
    description = "Выполнить shell-команду на сервере"
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Команда для выполнения"},
            "timeout": {"type": "integer", "default": 30}
        },
        "required": ["command"]
    }
    
    def execute(self, command: str, timeout: int = 30) -> str:
        import subprocess
        result = subprocess.run(
            command, shell=True, capture_output=True, 
            text=True, timeout=timeout
        )
        return result.stdout + result.stderr
```

#### Приоритет 2 (Фаза 2): Интеллектуальные API

```python
# tools/code_execution.py
class CodeExecutionTool:
    """Безопасное выполнение Python-кода."""
    name = "python_exec"
    description = "Выполнить Python-код в изолированном окружении"
    # ... через subprocess с ограничениями

# tools/document_reader.py  
class DocumentReaderTool:
    """Чтение и анализ документов."""
    name = "read_document"
    description = "Прочитать документ (PDF, DOCX, TXT, MD)"
    # ... через pymupdf, python-docx

# tools/image_analysis.py
class ImageAnalysisTool:
    """Анализ изображений через Vision LLM."""
    name = "analyze_image"
    description = "Проанализировать изображение"
    # ... через API с vision (GPT-4o, Claude)
```

#### Приоритет 3 (Фаза 3): Продвинутые интеграции

| API | Назначение | Библиотека |
|-----|-----------|-----------|
| **GitHub API** | Управление репозиториями | `PyGithub` / MCP |
| **Google Calendar** | Календарь и напоминания | `google-api-python-client` |
| **Notion API** | Заметки и документы | `notion-client` |
| **Stripe API** | Платежи | `stripe` |
| **Slack API** | Коммуникация | `slack-sdk` |
| **Weather API** | Погода | `python-weather` |
| **Email (SMTP)** | Отправка почты | `smtplib` |
| **RSS** | Новостные потоки | `feedparser` |

---

## 8. Оценка трудозатрат

| Фаза | Название | Трудозатраты | Приоритет |
|------|---------|-------------|-----------|
| **1** | Tool Calling + MCP | 4-6 недель | 🔴 Критический |
| **2** | Reasoning + Planning | 3-4 недели | 🔴 Критический |
| **3** | Multi-Agent + A2A | 4-6 недель | 🟡 Средний |
| **4** | Memory v2 + RAG | 3-4 недели | 🟡 Средний |
| **5** | Autonomy + WebUI | 4-6 недель | 🟢 Низкий |
| **6** | Marketplace + Distribution | 6-8 недель | 🟢 Низкий |
| **Итого** | | **24-34 недели** | |

---

## 9. Риски и митигация

| Риск | Вероятность | Влияние | Митигация |
|------|------------|---------|-----------|
| LLM галлюцинации в tool calling | Высокая | Высокое | Verification layer, sandbox execution |
| MCP-серверы нестабильны | Средняя | Среднее | Автоперезапуск, таймауты, fallback |
| Агент выполняет опасные команды | Средняя | Критическое | Whitelist команд, подтверждение owner'а |
| Memory leak (память растёт бесконечно) | Низкая | Среднее | Memory consolidation, quotas |
| A2A атаки (внешние агенты) | Низкая | Высокое | Аутентификация, sandbox |
| Стоимость API (LLM) | Средняя | Среднее | Кэширование, локальная fallback модель |
| Производительность на 2C/4GB | Высокая | Среднее | Локальная модель, оптимизация, queue |

---

## Итог

**Agent Smith** — это уже функционирующий автономный AI-агент с уникальными возможностями:

1. **Графовая память** (IKKF) — не имеет аналогов среди существующих решений
2. **Когнитивная петля** (сны → идеи → реализация) — креативный компонент
3. **Автосохранение + автозапись правил** — агент учится на каждом взаимодействии

**Ключевые шаги для развития:**

1. **Фаза 1 (Tool Calling + MCP)** — сделает агента полезным (поиск, файлы, команды)
2. **Фаза 2 (Reasoning)** — сделает агента умным (рассуждения, планирование)
3. **Фаза 3 (Multi-Agent)** — сделает агента масштабируемым (параллельные задачи)

**Самый быстрый ROI:** Фаза 1 (Tool Calling) — после её реализации агент сможет:
- Искать информацию в интернете
- Выполнять shell-команды
- Читать/записывать файлы
- Подключать внешние MCP-серверы

> *Нео сказал «I know kung fu». Морфиус ответил «Show me». Agent Smith говорит: «I'll do it myself — with tools.»*