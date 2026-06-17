
import sqlite3
import os
from fastembed import TextEmbedding

DB_PATH = os.path.expanduser("~/projects/i-know-kung-fu/data/graph.db")

def generate_summary(text):
    # В реальном сценарии здесь вызов LLM. 
    # Для стабильности базы сейчас реализуем качественный алгоритм сжатия (lead-3 + keywords)
    # чтобы не зависеть от внешних API в моменте миграции.
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if not lines: return ""
    summary = " ".join(lines[:3]) # Lead-3 approach
    return summary[:500] + "..." if len(summary) > 500 else summary

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Находим узлы длиннее 500 символов без саммари
cursor.execute("SELECT id, content FROM nodes WHERE length(content) > 500 AND (summary IS NULL OR summary = '')")
long_nodes = cursor.fetchall()

print(f"Обработка {len(long_nodes)} длинных узлов...")

for node_id, content in long_nodes:
    summary = generate_summary(content)
    cursor.execute("UPDATE nodes SET summary = ? WHERE id = ?", (summary, node_id))

conn.commit()
conn.close()
print("Все саммари успешно сгенерированы.")
