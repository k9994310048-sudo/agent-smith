#!/bin/bash
# Start IKKF Web UI on port 8767

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Активируем venv
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# Kill старый процесс если работает
fuser -k 8767/tcp 2>/dev/null || true

echo "🌐 Starting IKKF Web UI on http://127.0.0.1:8767"
python3 ikkf/webui.py
