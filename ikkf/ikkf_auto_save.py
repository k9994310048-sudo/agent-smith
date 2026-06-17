#!/usr/bin/env python3
"""
IKKF Auto-Save — Автоматическое сохранение новых сообщений из сессий Hermes в IKKF Graph.

Читает таблицу messages из ~/.hermes/state.db (session_id, role, content, timestamp).
Фильтрует только role='assistant' (мои ответы).
Извлекает ключевые факты из каждого ответа.
Сохраняет в IKKF Graph через API.
Пропускает уже сохранённые (dedup по content hash).

Запуск:
  python3 ikkf_auto_save.py --once      # Один раз
  python3 ikkf_auto_save.py --daemon    # Каждые 5 минут
  python3 ikkf_auto_save.py --since 3600  # За последний час
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
from datetime import datetime, timedelta

# ---- Config ----
IKKF_API = "http://127.0.0.1:8766"
HERMES_STATE_DB = os.path.expanduser("~/.hermes/state.db")
LOG_FILE = os.path.expanduser("~/.hermes/ikkf-auto-save.log")
PROGRESS_FILE = os.path.expanduser("~/.hermes/ikkf-auto-save-progress.json")

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

# ---- Fact extraction ----

def extract_facts(text):
    """Извлечь ключевые факты из текста ответа."""
    facts = []
    sentences = re.split(r'(?<=[.!?])\n|(?<=[.!?])\s+(?=[A-ZА-Я])', text)
    
    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 40:
            continue
        if sent.startswith("```") or sent.startswith("    "):
            continue
        if sent.startswith("---") or sent.startswith("==="):
            continue
        
        is_fact = False
        
        # Определения
        if any(w in sent for w in ["— это", "является", "означает", "представляет собой", "решает проблему"]):
            is_fact = True
        
        # Конкретные данные
        if re.search(r'\d+ (узел|связь|MB|ms|KB|ГБ|%)', sent):
            is_fact = True
        
        # Решения и выводы
        if any(w in sent for w in ["создан", "добавлен", "настроен", "установлен", "завершен", "решён", "решена", "реализова"]):
            is_fact = True
        
        # Правила и принципы
        if any(w in sent for w in ["правило", "принцип", "нужно", "должно", "всегда", "никогда", "обязательно"]):
            is_fact = True
        
        # Команды и конфигурации
        if any(w in sent for w in ["curl ", "systemctl", "pip3", "python3", "POST ", "GET "]):
            is_fact = True
        
        if is_fact:
            facts.append(sent[:500])
    
    return facts

# ---- Main logic ----

def get_new_messages(since_seconds=3600):
    """Получить новые сообщения assistant из Hermes state.db."""
    if not os.path.exists(HERMES_STATE_DB):
        log(f"ERROR: {HERMES_STATE_DB} not found")
        return []
    
    conn = sqlite3.connect(HERMES_STATE_DB)
    conn.row_factory = sqlite3.Row
    
    # Timestamp в state.db — Unix epoch (float)
    since_ts = time.time() - since_seconds
    
    rows = conn.execute("""
        SELECT m.id, m.session_id, m.role, m.content, m.timestamp, s.title
        FROM messages m
        LEFT JOIN sessions s ON m.session_id = s.id
        WHERE m.role = 'assistant'
          AND m.timestamp > ?
          AND m.content IS NOT NULL
          AND LENGTH(m.content) > 100
        ORDER BY m.timestamp ASC
    """, (since_ts,)).fetchall()
    
    conn.close()
    return rows

def process_messages(messages):
    """Обработать сообщения и сохранить факты в IKKF."""
    if not messages:
        log("No new messages to process")
        return 0
    
    log(f"Processing {len(messages)} messages")
    
    progress = load_progress()
    saved = 0
    skipped = 0
    
    for msg in messages:
        msg_id = msg["id"]
        
        # Пропускаем уже обработанные
        if msg_id in progress.get("processed_ids", []):
            skipped += 1
            continue
        
        content = msg["content"]
        facts = extract_facts(content)
        
        # Конвертируем timestamp из Unix epoch в ISO
        ts = msg["timestamp"]
        if isinstance(ts, (int, float)):
            ts_iso = datetime.utcfromtimestamp(ts).isoformat()
        else:
            ts_iso = str(ts)
        
        for fact in facts:
            # Проверяем дубликат
            try:
                h = hashlib.md5(fact.strip().lower().encode()).hexdigest()[:12]
                existing = ikkf_get(f"/search?q={urllib.parse.quote(fact[:80])}&limit=3")
                is_dup = False
                for r in existing.get("results", []):
                    if hashlib.md5(r["node"]["content"].strip().lower().encode()).hexdigest()[:12] == h:
                        is_dup = True
                        break
                
                if is_dup:
                    continue
                
                # Сохраняем
                ikkf_post("/node", {
                    "content": fact,
                    "node_type": "fact",
                    "importance": 0.75,
                    "tags": ["auto-save", f"session-{msg['session_id'][:8]}"],
                    "project": "conversation-log",
                    "context": {
                        "semantic": "автосохранение",
                        "temporal": ts_iso[:10]
                    }
                })
                saved += 1
                log(f"  Saved: {fact[:80]}...")
            except Exception as e:
                log(f"  Error: {e}")
        
        # Отмечаем как обработанное
        progress.setdefault("processed_ids", []).append(msg_id)
        progress["last_message_id"] = msg_id
    
    save_progress(progress)
    log(f"Results: {saved} saved, {skipped} already processed")
    return saved

def run_once(since_seconds=3600):
    log("=== IKKF Auto-Save started ===")
    messages = get_new_messages(since_seconds)
    saved = process_messages(messages)
    log(f"=== Completed: {saved} facts saved ===")
    return saved

def run_daemon(interval=300):
    log(f"=== Daemon started (interval: {interval}s) ===")
    while True:
        try:
            run_once(since_seconds=interval + 60)
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
    parser.add_argument("--interval", type=int, default=300)
    args = parser.parse_args()
    
    if args.daemon:
        run_daemon(args.interval)
    else:
        run_once(args.since)
