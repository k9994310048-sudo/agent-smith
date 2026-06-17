#!/bin/bash
# IKKF — Ночная консолидация графа знаний
# Останавливает API, делает работу, запускает обратно
# Подробный лог в logs/consolidate-YYYY-MM-DD.log

cd /root/projects/i-know-kung-fu

LOG_DIR="logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/consolidate-$(date +%Y-%m-%d_%H%M%S).log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "=========================================="
log "Консолидация начата"
log "=========================================="
log "До консолидации:"
log "  $(curl -s http://127.0.0.1:8766/stats 2>/dev/null | python3 -c "import sys,json; r=json.load(sys.stdin); print(f'Nodes: {r[\"nodes_total\"]}, Edges: {r[\"edges_total\"]}')" 2>/dev/null || echo 'API stats unavailable')"

# Останавливаем API
log "Остановка API..."
systemctl stop ikkf-graph
sleep 2

# Запускаем консолидацию с логированием
/usr/bin/python3 -c "
from graph.graph import Graph
from graph.consolidation import Consolidator
import json, time, sys

class LogWriter:
    def __init__(self, log_file):
        self.f = open(log_file, 'a')
    def write(self, msg):
        self.f.write(f'[{time.strftime(\"%H:%M:%S\")}] {msg}\\n')
        self.f.flush()
    def close(self):
        self.f.close()

lw = LogWriter('$LOG_FILE')
old_print = print
def log_print(*args, **kwargs):
    old_print(*args, **kwargs)
    lw.write(' '.join(str(a) for a in args))
print = log_print

g = Graph('data/graph.db')
c = Consolidator(g)

start = time.time()
stats = c.run(full=True)
elapsed = time.time() - start

print(f'=== Консолидация завершена за {elapsed:.1f}s ===')
print(f'Stats: {json.dumps(stats, indent=2)}')
print(f'Graph after: {json.dumps(g.stats(), indent=2)}')
g.close()
lw.close()
" 2>&1 | tee -a "$LOG_FILE"

EXIT_CODE=${PIPESTATUS[0]}

# Запускаем API обратно
log "Запуск API..."
systemctl start ikkf-graph
sleep 3

# Проверяем
if systemctl is-active ikkf-graph >/dev/null 2>&1; then
    AFTER=$(curl -s http://127.0.0.1:8766/stats 2>/dev/null | python3 -c "import sys,json; r=json.load(sys.stdin); print(f'Nodes: {r[\"nodes_total\"]}, Edges: {r[\"edges_total\"]}')" 2>/dev/null || echo 'unavailable')
    log "API работает. После консолидации: $AFTER"
    log "=========================================="
    log "Результат: ОК (exit=$EXIT_CODE)"
else
    log "❌ API не запустился!"
    log "=========================================="
    log "Результат: FAIL (exit=$EXIT_CODE)"
fi

# Оставляем только последние 10 логов
ls -t "$LOG_DIR"/consolidate-*.log 2>/dev/null | tail -n +11 | xargs rm -f 2>/dev/null

echo "Log saved: $LOG_FILE"
