#!/usr/bin/env python3
"""
IKKF Rule Capture — Авто-запись правил из коррекций пользователя.

Это апгрейд самообучения уровня знаний: агент сам замечает моменты,
когда пользователь его поправил, формулирует из этого правило и
сохраняет в IKKF Graph как узел type=skill с тегом rule:auto.

Как работает:
  1. Читает ~/.hermes/state.db (таблица messages).
  2. Находит сообщения role='user', содержащие сигнал коррекции
     ("не так", "я же просил", "не делай", "неправильно" и т.д.).
  3. Берёт предыдущий ответ assistant как контекст ошибки.
  4. Локальный Qwen формулирует короткое правило на будущее.
  5. Сохраняет в IKKF (dedup по хэшу — одно правило не пишется дважды).

Принципы:
  - Не трогает рабочий цикл и API — отдельный автономный наблюдатель.
  - Если Qwen недоступен — fallback: сохраняет сырую коррекцию как правило.
  - Прогресс отслеживается, чтобы не обрабатывать одно дважды.

Запуск:
  python3 ikkf_rule_capture.py --once            # один проход за последний час
  python3 ikkf_rule_capture.py --since 86400     # за сутки
  python3 ikkf_rule_capture.py --dry-run         # ничего не сохранять, только показать
  python3 ikkf_rule_capture.py --daemon          # каждые 10 минут
"""

import os
import sys
import json
import hashlib
import time
import re
import sqlite3
import urllib.request
import urllib.parse
from datetime import datetime

# ---- Config ----
IKKF_API = "http://127.0.0.1:8766"
HERMES_STATE_DB = os.path.expanduser("~/.hermes/state.db")
LOG_FILE = os.path.expanduser("~/.hermes/ikkf-rule-capture.log")
PROGRESS_FILE = os.path.expanduser("~/.hermes/ikkf-rule-capture-progress.json")

# Сигналы коррекции в сообщениях пользователя (рус + англ).
# Намеренно консервативный список — лучше пропустить, чем нагенерить мусора.
CORRECTION_SIGNALS = [
    "не так", "не то", "неправильно", "неверно", "ошиб",
    "я же просил", "я просил", "я не просил", "я не об этом",
    "не делай", "не надо", "не нужно было", "зачем ты",
    "перестань", "прекрати", "стоп", "остановись",
    "я же говорил", "сколько раз", "опять", "снова не",
    "не то что я", "не это", "это не то", "испортил", "сломал",
    "моё терпение", "мое терпение", "терпение на исходе",
    "делай только что я", "ничего лишнего", "не выдумывай",
    "не выдавай желаемое",
    # англ
    "that's wrong", "thats wrong", "not what i", "don't do",
    "stop doing", "i asked", "i didn't ask", "you broke",
]

# ---- Logging ----

def log(msg):
    ts = datetime.utcnow().isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

# ---- IKKF API ----

def ikkf_post(path, data):
    url = f"{IKKF_API}{path}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def ikkf_get(path):
    with urllib.request.urlopen(f"{IKKF_API}{path}", timeout=10) as r:
        return json.loads(r.read())

# ---- Progress tracking ----

def load_progress():
    try:
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    except Exception:
        return {"last_message_id": 0, "processed_ids": []}

def save_progress(progress):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f)

# ---- Local LLM (lazy) ----

_llm = None

def get_llm():
    """Ленивая загрузка Qwen. None если недоступна — тогда работает fallback."""
    global _llm
    if _llm is None:
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from kungfu_llm import KungFuLLM
            _llm = KungFuLLM()
            # триггерим загрузку, чтобы поймать FileNotFoundError тут
            _ = _llm.llm
        except Exception as e:
            log(f"LLM недоступна ({e}) — работаю в fallback-режиме")
            _llm = False
    return _llm or None

def formulate_rule(user_correction, assistant_context):
    """Сформулировать правило из коррекции. Qwen, иначе fallback."""
    llm = get_llm()
    if llm is not None:
        prompt = f"""You analyze a dialogue moment where a user corrected an AI assistant, and you extract a behavioural rule for the assistant's future actions. Reply ONLY valid JSON, no other text.

If the user message is NOT actually correcting the assistant's behaviour (e.g. it is just a new request, a greeting, or frustration with no specific instruction), set "is_rule" to false.

If it IS a correction, write a short rule (max 18 words, in Russian) in the form of what the assistant SHOULD do next time. Be concrete.

Assistant did (context): "{assistant_context[:400]}"
User correction: "{user_correction[:400]}"

Format: {{"is_rule": true/false, "rule": "...", "importance": 0.0-1.0}}

JSON:"""
        try:
            raw = llm._ask(prompt, max_tokens=200, temperature=0.1)
            js = llm._extract_json(raw)
            if js:
                data = json.loads(js)
                if data.get("is_rule") is False:
                    return None, 0.0
                rule = (data.get("rule") or "").strip()
                if rule and len(rule) > 5:
                    imp = data.get("importance", 0.8)
                    try:
                        imp = min(1.0, max(0.0, float(imp)))
                    except Exception:
                        imp = 0.8
                    return rule, imp
        except Exception as e:
            log(f"  LLM formulate error: {e} — fallback")

    # Fallback: сохраняем коррекцию как сырое правило
    rule = f"Пользователь поправил: «{user_correction.strip()[:200]}» — учесть впредь."
    return rule, 0.8

# ---- Detection ----

# Префиксы/маркеры системных и служебных вставок — это НЕ коррекции пользователя.
SYSTEM_MARKERS = (
    "[context compaction", "[system note", "[out-of-band",
    "[reference only", "earlier turns were compacted",
    "your previous turn was interrupted",
)

# Настоящая коррекция от человека — короткая живая реплика, не простыня.
MAX_CORRECTION_LEN = 600

def is_correction(text):
    t = text.strip()
    low = t.lower()
    # Отсекаем системные/служебные вставки
    if any(low.startswith(m) or m in low[:120] for m in SYSTEM_MARKERS):
        return False
    # Отсекаем слишком длинные блоки (это запрос/контекст, а не правка)
    if len(t) > MAX_CORRECTION_LEN:
        return False
    return any(sig in low for sig in CORRECTION_SIGNALS)

def get_user_messages(since_seconds=3600):
    """Сообщения пользователя за период + предыдущий ответ assistant как контекст."""
    if not os.path.exists(HERMES_STATE_DB):
        log(f"ERROR: {HERMES_STATE_DB} not found")
        return []

    conn = sqlite3.connect(HERMES_STATE_DB)
    conn.row_factory = sqlite3.Row
    since_ts = time.time() - since_seconds

    # Тянем всю ленту сессий за период, чтобы можно было найти
    # предыдущий ответ assistant для каждой пользовательской коррекции.
    rows = conn.execute("""
        SELECT m.id, m.session_id, m.role, m.content, m.timestamp
        FROM messages m
        WHERE m.timestamp > ?
          AND m.content IS NOT NULL
        ORDER BY m.session_id ASC, m.timestamp ASC, m.id ASC
    """, (since_ts,)).fetchall()

    conn.close()
    return rows

def build_correction_pairs(rows):
    """Из ленты собрать пары (user_correction, prev_assistant_context)."""
    pairs = []
    last_assistant = {}  # session_id -> last assistant content
    for m in rows:
        sid = m["session_id"]
        role = m["role"]
        content = m["content"] or ""
        if role == "assistant":
            last_assistant[sid] = content
        elif role == "user":
            if len(content.strip()) >= 3 and is_correction(content):
                pairs.append({
                    "id": m["id"],
                    "session_id": sid,
                    "user": content,
                    "context": last_assistant.get(sid, ""),
                    "timestamp": m["timestamp"],
                })
    return pairs

# ---- Save ----

def rule_hash(rule):
    return hashlib.md5(rule.strip().lower().encode()).hexdigest()[:12]

def is_duplicate(rule):
    """Проверить, есть ли уже такое правило (по хэшу среди похожих)."""
    try:
        h = rule_hash(rule)
        existing = ikkf_get(f"/search?q={urllib.parse.quote(rule[:80])}&limit=5")
        for r in existing.get("results", []):
            node = r.get("node", r)
            content = node.get("content", "")
            if rule_hash(content) == h:
                return True
    except Exception:
        pass
    return False

def save_rule(rule, importance, pair, dry_run=False):
    ts = pair["timestamp"]
    if isinstance(ts, (int, float)):
        ts_iso = datetime.utcfromtimestamp(ts).isoformat()
    else:
        ts_iso = str(ts)

    payload = {
        "content": rule,
        "node_type": "skill",
        "importance": importance,
        "tags": ["rule:auto", "self-learning", f"session-{pair['session_id'][:8]}"],
        "project": "auto-rules",
        "context": {
            "semantic": "правило-поведения",
            "social": "klim",
            "temporal": ts_iso[:10],
            "emotional": "negative",  # правило родилось из коррекции
        },
    }
    if dry_run:
        log(f"  [DRY-RUN] would save rule: {rule}")
        return True
    try:
        ikkf_post("/node", payload)
        log(f"  ✅ Saved rule: {rule}")
        return True
    except Exception as e:
        log(f"  Error saving rule: {e}")
        return False

# ---- Main ----

def run_once(since_seconds=3600, dry_run=False):
    log("=== IKKF Rule Capture started ===")
    rows = get_user_messages(since_seconds)
    pairs = build_correction_pairs(rows)
    log(f"Found {len(pairs)} correction signals in last {since_seconds}s")

    if not pairs:
        log("=== Completed: 0 rules ===")
        return 0

    progress = load_progress()
    saved = 0
    skipped = 0

    for pair in pairs:
        if pair["id"] in progress.get("processed_ids", []):
            skipped += 1
            continue

        rule, importance = formulate_rule(pair["user"], pair["context"])

        if not rule:
            log(f"  (skip, не правило) {pair['user'][:60]}")
        elif is_duplicate(rule):
            log(f"  (dup) {rule[:70]}")
        else:
            if save_rule(rule, importance, pair, dry_run=dry_run):
                saved += 1

        if not dry_run:
            progress.setdefault("processed_ids", []).append(pair["id"])
            progress["last_message_id"] = pair["id"]

    if not dry_run:
        save_progress(progress)

    log(f"=== Completed: {saved} rules saved, {skipped} already processed ===")
    return saved

def run_daemon(interval=600):
    log(f"=== Rule Capture daemon started (interval: {interval}s) ===")
    while True:
        try:
            run_once(since_seconds=interval + 120)
        except Exception as e:
            log(f"Error: {e}")
        time.sleep(interval)

# ---- CLI ----

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--since", type=int, default=3600)
    parser.add_argument("--interval", type=int, default=600)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.daemon:
        run_daemon(args.interval)
    else:
        run_once(args.since, dry_run=args.dry_run)
