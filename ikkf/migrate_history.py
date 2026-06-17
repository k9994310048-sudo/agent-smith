#!/usr/bin/env python3
"""
Миграция: добавить колонку history в существующую базу IKKF.

Безопасно: только добавляет колонку, не трогает данные.
Идемпотентно: можно запускать повторно.
"""

import os
import sys
import sqlite3
import json

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "graph.db")

def migrate():
    conn = sqlite3.connect(DB_PATH)
    # проверяем есть ли уже колонка
    cols = [row[1] for row in conn.execute("PRAGMA table_info(nodes)").fetchall()]
    if "history" in cols:
        print("Колонка history уже существует, миграция не нужна")
        conn.close()
        return

    print("Добавляю колонку history...")
    conn.execute("ALTER TABLE nodes ADD COLUMN history TEXT DEFAULT '[]'")
    conn.commit()

    # проверяем результат
    count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    print(f"Миграция завершена. Узлов в базе: {count}")
    conn.close()

if __name__ == "__main__":
    migrate()
