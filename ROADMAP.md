# Agent Smith — Roadmap & Change Log

> Проект: `/home/mac/.agent-smith`
> MacBook Pro 2012, i5-2435M, 16GB DDR3L, Ubuntu 24.04
> Обновлено: 2026-06-17 08:00

---

## Текущий статус (v4.8)

| Компонент | Статус | Порт/Путь |
|-----------|--------|-----------|
| Agent Smith v4.8 | ✅ Работает | `main.py` |
| IKKF Graph API | ✅ Работает | `127.0.0.1:8766` |
| DeepSeek-R1 1.5B Q4_K_M | ✅ llama-server | `127.0.0.1:8081` |
| Qwen 2.5 0.5B Q4_K_M | ✅ llama-server | `127.0.0.1:8080` |
| Telegram Bot @AgentSmity42_bot | ✅ Подключён | config.yaml |
| Web Dashboard | ✅ Запущен | `127.0.0.1:8768` |
| Dream Pipeline | ✅ Работает | cron 3:00 (сны), 6:00 (ранжирование) |
| Skill Learning | ✅ Работает | `agents/skill_learner.py` |
| Fact Verification | ✅ Работает | `verified` поле, `contradiction_check()` |
| Self-Awareness | ✅ Работает | `memory_awareness.assess()` + `self_reflection()` |
| Multimodal (TTS + Whisper) | ✅ Работает | edge-tts + whisper tiny |
| Self-Healing | ✅ Работает | `agents/autonomy/self_repair.py` |
| Auto-save IKKF | ✅ Каждые 5 мин | cron |
| Backup | ✅ Каждую ночь 2:00 | cron |
| systemd автозапуск | ✅ Настроен | `agent-smith.service` |

---

## Архитектура

```
┌─────────────────────────────────────────────────┐
│              Agent Smith v4.8                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ Perceive │→ │  Reason  │→ │   Act    │       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘       │
│       │              │              │             │
│       └──────────────┼──────────────┘             │
│                      │                            │
│  ┌───────────────────▼────────────────────┐      │
│  │           LLM Provider                  │      │
│  │  Primary: kodikrouter/owl-alpha (API)   │      │
│  │  Fallback: DeepSeek-R1 1.5B (local)     │      │
│  └───────────────────┬────────────────────┘      │
│                      │                            │
│  ┌───────────────────▼────────────────────┐      │
│  │           IKKF Bridge                   │      │
│  └───────────────────┬────────────────────┘      │
│                      │                            │
├──────────────────────┼────────────────────────────┤
│  ┌───────────────────▼────────────────────┐      │
│  │        IKKF Graph API (8766)            │      │
│  │  SQLite + FTS5 + Vector                 │      │
│  │  verified, source, source_type           │      │
│  └───────────────────┬────────────────────┘      │
│                      │                            │
│  ┌───────────────────▼────────────────────┐      │
│  │  Cognitive Loop (core_system.py)        │      │
│  │  • Dream cycle (spawn subprocess)       │      │
│  │  • Self-correction (LLM check)          │      │
│  │  • Self-reflection (post-response)      │      │
│  │  • State: awake → idle → sleeping       │      │
│  └─────────────────────────────────────────┘      │
│                                                   │
│  ┌─────────────────────────────────────────┐      │
│  │  Self-Healing (self_repair.py)          │      │
│  │  • Диагностика сервисов                 │      │
│  │  • Автоперезапуск при падении           │      │
│  │  • Восстановление БД из бэкапа          │      │
│  └─────────────────────────────────────────┘      │
│                                                   │
│  ┌─────────────────────────────────────────┐      │
│  │  Memory Awareness (memory_awareness.py) │      │
│  │  • coverage, freshness, gaps            │      │
│  │  • should_admit_ignorance               │      │
│  └─────────────────────────────────────────┘      │
│                                                   │
│  ┌─────────────────────────────────────────┐      │
│  │  Multimodal                             │      │
│  │  • TTS: edge-tts (ru-RU-SvetlanaNeural) │      │
│  │  • Whisper: tiny model (распознавание)  │      │
│  └─────────────────────────────────────────┘      │
│                                                   │
│  ┌─────────────────────────────────────────┐      │
│  │  Scheduled Tasks (cron)                  │      │
│  │  */5 min  → ikkf_auto_save               │      │
│  │  2:00     → backup graph.db              │      │
│  │  3:00     → dream cycle                  │      │
│  │  4:00     → consolidation                 │      │
│  │  6:00     → dream pipeline (ранжирование)│      │
│  └─────────────────────────────────────────┘      │
└─────────────────────────────────────────────────┘
```

---

## История изменений
### v5.0 — Полноценный веб-поиск (2026-06-17)**Выполнено:**- [x] **OpenSERP** — запущен на макбуке в Docker (, Docker автозагрузка)- [x] **web_search v6.0** — OpenSERP (Bing+Yandex+Google+DDG+Baidu) + fallback на Wikipedia + DDG Instant- [x] Без API-ключа, без лимитов, полностью автономный (локальный Docker-контейнер)- [x] Megasearch — агрегация всех движков с дедупликацией и AI-сводкой- [x] Протестирован: поиск по "artificial intelligence 2024" → 5 качественных результатов**Ключевые изменения:**-  — переписан на OpenSERP (v6.0)- Docker:  контейнер, порт 7000---

### v5.0 — Полноценный веб-поиск (2026-06-17)

**Выполнено:**
- [x] **OpenSERP** — запущен на макбуке в Docker (restart=always, Docker автозагрузка)
- [x] **web_search v6.0** — OpenSERP (Bing+Yandex+Google+DDG+Baidu) + fallback на Wikipedia + DDG Instant
- [x] Без API-ключа, без лимитов, полностью автономный (локальный Docker-контейнер)
- [x] Megasearch — агрегация всех движков с дедупликацией и AI-сводкой
- [x] Протестирован: поиск по "artificial intelligence 2024" → 5 качественных результатов

**Ключевые изменения:**
- `agents/tools/web_search.py` — переписан на OpenSERP (v6.0)
- Docker: karust/openserp контейнер, порт 7000

---

### v4.9 — Стабильность и надёжность (2026-06-16)

**Выполнено:**
- [x] **P0-A:** `get_system_stats` — заглушка заменена на реальный сбор данных (uptime, load, RAM, disk, temp)
- [x] **P0-B:** Циклы инструментов — повторы считаются по name+args (не только name), лимит 2, сброс между итерациями
- [x] **P0-C:** Убраны неэффективные правила 5/6 из промпта, добавлено правило: "КАЖДОЕ утверждение — подкрепляй вызовом инструмента"
- [x] **P0-D:** `self_reflection()` интегрирован в `process_message_stream` — вызывается после первой итерации
- [x] **P1-A:** `process_message_stream` разбит на подметоды: `_build_messages`, `_run_llm_iteration`, `_execute_tool`, `_should_skip_tool`
- [x] **P1-B:** Rate limiting — экспоненциальный бекофф при 429 (Retry-After, 3 попытки, 10s→20s→40s)
- [x] **P2-A:** PerformanceMonitor — отслеживание времени ответа, количества инструментов, ошибок
- [x] **P2-B:** Device Adapter — сканирование железа (CPU, RAM, disk, GPU, temp), подбор модели, сохранение профиля

**Ключевые изменения в файлах:**
- `agents/tools/system_tools.py` — реальный get_system_stats
- `agents/smith.py` — подметоды, кэш результатов, сброс счётчика, self_reflection
- `agents/llm_provider.py` — экспоненциальный бекофф при 429
- `agents/core_system.py` — PerformanceMonitor
- `agents/device_adapter.py` — новый модуль

---

### v4.8 — Верификация, самосознание, мультимодальность (2026-06-16)

**Выполнено:**
- [x] Верификация фактов: `verified` поле в Node/Graph/Storage/API
- [x] Автоматическая верификация при консолидации (confidence > 0.8)
- [x] `contradiction_check()` через embedding similarity (порог 0.85)
- [x] `memory_awareness.assess()` расширен: freshness + should_admit_ignorance
- [x] `self_reflection()` — проверка после ответа
- [x] TTS через edge-tts (установлен, работает ~2 сек на 32KB)
- [x] Whisper tiny для распознавания речи (установлен)
- [x] Инструменты tts и whisper зарегистрированы в tool_registry (7 инструментов)
- [x] Удаление дубликатов кода: smith.py 861 → 491 строка
- [x] systemd автозапуск: `agent-smith.service` (enabled, Restart=always)

---

### v4.7 — Расширенный план развития (2026-06-15 12:00)

### Added to plan by user
1. **IKKF_SH** — учтён как слой действий поверх IKKF (skills, reasoning, planner, verification)
2. **Web Account Proxy** — использование бесплатных веб-аккаунтов нейросетей через браузер (экономия токенов ~90%)
3. **Multi-API Router** — неограниченное количество API с авто-маршрутизацией и failover
4. **Telegram команды для управления API** — /add_api, /switch_model, /list_apis

---

### v4.6 — Агент-инициированный аудит (2026-06-15 10:00)

#### Ресурсы ПК (подтверждено)
| Параметр | Значение | Оценка |
|----------|----------|--------|
| CPU | i5-2435M (2C/4T, 2.4 ГГц) | ⚠️ Слабое звено |
| RAM | 16 ГБ (доступно ~12 ГБ) | ✅ Достаточно |
| Диск | 116 ГБ (свободно 31 ГБ, 73% занято) | ⚠️ Мало места |
| GPU | Нет (Intel HD 3000) | ❌ Нет CUDA |

---

### v4.5 — Fix quality of responses (2026-06-15)

**Fixes applied:**
1. Detailed architecture analysis prompt with web_search priority
2. Tool call limit: 8→12 for complex analysis
3. Long message split: >4000 chars split into multiple messages
4. Markdown to Telegram HTML converter
5. Self-check prompt: verify all request points covered
6. Emoji restored in yield messages (UTF-8 safe)
7. max_tokens: 2048 for tool results, 3000 for final answer
8. 400/429 handling: fallback to plain text

---

### v4.4 — Fix: зависание на tool-calls (2026-06-15 09:16)

**Исправления:**
| # | Файл | Что сделано |
|---|------|-------------|
| 1 | agents/smith.py | Прогресс yield перед каждым tool-call и после итерации |
| 2 | agents/smith.py | Лимит MAX_TOOL_CALLS=8, потом tools=None для финального ответа |
| 3 | agents/llm_provider.py | Таймаут 100→45с + 1 retry с обрезанным контекстом |
| 4 | agents/smith.py | Формат ответа в промпте: план → инструменты → итог |
| 5 | agents/smith.py | Очистка tool-messages после 6+ (keep last 4) |
| 6 | integrations/telegram.py | Throttle 1.2→2.5с + обработка 429 (Retry-After) |

---

### v4.3 — Первый запуск (2026-06-15)

- Аудит всех компонентов
- Запуск IKKF API на Макбуке
- `ikkf_dream.py` — генерация снов через DeepSeek-R1
- Cron: автосохранение, бэкап, сны, идеи

---

### v4.2 — Первоначальная настройка (2026-06-14)

- Agent Smith запущен впервые
- Telegram бот подключён
- IKKF интегрирован

---

## Планы / TODO

### Высший приоритет
- [ ] Проверить что cron сны работают (посмотреть логи через день)
- [ ] Проверить dream pipeline на реальных данных
- [ ] Интерактивное обсуждение проектов с пользователем

### Средний приоритет
- [ ] Добавить утренний бонус — отправлять лучшую идею дня в Telegram
- [ ] Увеличить контекст DeepSeek-R1 до 4096 (сейчас 2084)
- [ ] Оптимизировать RAM — выгружать LLM при неиспользовании

### Исследование
- [ ] Phi-3-mini 3.8B Q4 — 2.1 GB RAM, длинный контекст 128K
- [ ] Автоматический failover: API → DeepSeek-R1 → Qwen 0.5B

---

## Fast Reference

```bash
# Перезапуск Agent Smith (systemd)
sudo systemctl restart agent-smith.service

# Перезапуск вручную
cd ~/.agent-smith && pkill -f main.py && source venv/bin/activate && nohup python main.py > /tmp/agent.log 2>&1 &

# Перезапуск IKKF API
cd ~/.agent-smith && pkill -f "uvicorn ikkf.api" && source venv/bin/activate && nohup python3 -m uvicorn ikkf.api:app --host 127.0.0.1 --port 8766 > /tmp/ikkf-api.log 2>&1 &

# Перезапуск DeepSeek-R1
pkill -f "llama-server.*deepseek" && nohup ~/llama.cpp/build/bin/llama-server -m ~/.agent-smith/models/deepseek-r1-1.5b/DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf -c 2048 --host 0.0.0.0 --port 8081 -t 2 -b 512 > /tmp/deepseek.log 2>&1 &

# Тест сна вручную
cd ~/.agent-smith && python3 ikkf/ikkf_dream.py --once --dry-run

# Проверка здоровья
curl -s http://127.0.0.1:8766/health
curl -s http://127.0.0.1:8081/health 2>/dev/null || curl -s http://127.0.0.1:8080/health 2>/dev/null

# Логи
tail -f ~/.agent-smith/system.log        # Agent Smith
tail -f ~/.agent-smith/data/dream.log     # Сны
tail -f /tmp/ikkf-api.log                 # IKKF API

# Статус systemd
sudo systemctl status agent-smith.service
```

---

## Модели

| Модель | Формат | RAM | Скорость | Путь |
|--------|--------|-----|----------|------|
| DeepSeek-R1 1.5B | Q4_K_M | ~1.1 GB | ~5 t/s | `~/.agent-smith/models/deepseek-r1-1.5b/` |
| Qwen 2.5 0.5B | Q4_K_M | ~0.5 GB | ~20 t/s | `~/models/qwen2.5-0.5b-instruct-q4_k_m.gguf` |
| BitNet b1.58 2B | i2_s | ~0.4 GB | N/A (не работает) | `~/models/bitnet/ggml-model-i2_s.gguf` |

---

## Инструменты (tool_registry)

| Инструмент | Описание | Статус |
|------------|----------|--------|
| web_search | Поиск в интернете (OpenSERP: Bing+Yandex+Google+DDG+Baidu, Wikipedia fallback) | ✅ v5.0 |
| shell_exec | Выполнение команд (с безопасными ограничениями) | ✅ |
| file_read | Чтение файлов проекта (до 1500 символов) | ✅ |
| project_overview | Структура проекта (листинг директорий) | ✅ |
| get_system_stats | Реальные: uptime, load, RAM, disk, CPU temp | ✅ v4.9 |
| tts | Синтез речи (edge-tts, ru-RU-SvetlanaNeural) | ✅ |
| whisper | Распознавание речи (Whisper tiny) | ✅ |

---

*Последнее обновление: 2026-06-16 21:20*
