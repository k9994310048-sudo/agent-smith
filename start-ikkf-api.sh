#!/bin/bash
# Start IKKF Graph API on port 8766

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Активируем venv
source venv/bin/activate

# Создаём data dir если нужно
mkdir -p data

# Kilл старый процесс если работает
fuser -k 8766/tcp 2>/dev/null || true

# Запускаем API
echo "🧠 Starting IKKF Graph API on http://127.0.0.1:8766"
echo "📊 Database: $PROJECT_DIR/data/graph.db"
echo ""

python3 -m uvicorn ikkf.api:app \
    --host 127.0.0.1 \
    --port 8766 \
     \
    --log-level info
