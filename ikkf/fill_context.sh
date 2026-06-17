#!/bin/bash
# IKKF — Заполнение context dimensions (spatial/emotional/social) через LLM
# Запускать когда API остановлен или в maintenance window

cd /root/projects/i-know-kung-fu

echo "[$(date)] fill_context started"

# Останавливаем API чтобы не было DB lock
systemctl stop ikkf-graph
sleep 2

python3 << 'PYEOF' > data/fill_context.log 2>&1
import sqlite3, json, time, re, os
from graph.kungfu_llm import KungFuLLM
from graph.storage import Storage

DB_PATH = "data/graph.db"
start_time = time.time()

store = Storage(DB_PATH)
llm = KungFuLLM(n_ctx=512, n_threads=2)

# Находим узлы с пустыми spatial/emotional/social
rows = store.conn.execute(
    'SELECT id, content, context FROM nodes WHERE status="active"'
).fetchall()

to_fill = []
for r in rows:
    try:
        ctx = json.loads(r[2] or '{}')
    except:
        ctx = {}
    # Пропускаем если уже заполнено
    has_all = all(ctx.get(d) not in [None, 'null', 'None', ''] for d in ['spatial', 'emotional', 'social'])
    if not has_all and r[1] and len(r[1].strip()) > 10 and not r[1].startswith('/'):
        to_fill.append((r[0], r[1], ctx))

print(f"Nodes to fill: {len(to_fill)}")

filled = 0
errors = 0
committed = 0

for i, (nid, content, ctx) in enumerate(to_fill):
    text = content[:250]  # Ограничиваем длину
    
    try:
        prompt = f"""Analyze this text and extract context dimensions. Reply ONLY valid JSON, no other text.

Text: "{text}"

Required JSON format: {{"spatial": "location/place or null", "emotional": "positive/negative/neutral/null", "social": "person/group names or null"}}

Rules:
- spatial: where does this happen? (city, room, online, etc) or null
- emotional: what emotion is expressed? or null  
- social: who is mentioned? (names, groups) or null
- Use null (not "null") for unknown values

JSON:"""
        
        result = llm._ask(prompt, max_tokens=100, temperature=0.0)
        json_match = re.search(r'\{[^{}]*\}', result, re.DOTALL)
        
        if json_match:
            data = json.loads(json_match.group())
            updated = False
            for dim in ['spatial', 'emotional', 'social']:
                val = data.get(dim)
                if val and str(val).lower() not in ['null', 'none', '']:
                    ctx[dim] = str(val)[:100]
                    updated = True
            
            if updated:
                store.conn.execute(
                    'UPDATE nodes SET context = ? WHERE id = ?',
                    (json.dumps(ctx), nid)
                )
                filled += 1
                committed += 1
        
        # Коммит каждые записи чтобы не потерять прогресс
        if committed >= 10:
            store.conn.commit()
            committed = 0
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            remaining = (len(to_fill) - i - 1) / rate if rate > 0 else 0
            print(f"  Progress: {i+1}/{len(to_fill)}, filled: {filled}, {rate:.1f} nodes/sec, ETA: {remaining/60:.0f}min")
        
    except Exception as e:
        errors += 1
        continue

# Финальный коммит
store.conn.commit()
elapsed = time.time() - start_time
print(f"\nDone! Filled: {filled}/{len(to_fill)}, Errors: {errors}, Time: {elapsed/60:.1f}min")

store.conn.close()
PYEOF

echo "[$(date)] fill_context done"

# Запускаем API обратно
systemctl start ikkf-graph
sleep 2

if systemctl is-active ikkf-graph >/dev/null 2>&1; then
    echo "[$(date)] API started"
else
    echo "[$(date)] ❌ API failed to start!"
fi
