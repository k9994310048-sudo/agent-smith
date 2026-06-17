#!/usr/bin/env bash
# run-all.sh — Унифицированный запуск Agent Smith (v2.1 Async)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "==========================================="
echo "   Agent Smith — Unified Async Startup"
echo "==========================================="

# 1. Тотальная очистка
echo "🧹 Зачистка портов и процессов..."
fuser -k 8766/tcp 8767/tcp 8768/tcp 2>/dev/null || true
pkill -9 -f "python3 main.py" || true
sleep 1

# 2. Активация venv
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# 3. Запуск основного ядра (main.py теперь управляет всем)
echo "🚀 Запуск Унифицированного Ядра..."
echo "-------------------------------------------"

# Запускаем с приоритетом (nice), чтобы система была отзывчивой
nice -n 10 python3 -u main.py
