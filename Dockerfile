# Agent Smith — Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Копирование зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода проекта
COPY . .

# Создание директорий для данных
RUN mkdir -p /root/.agent-smith/data \
    && mkdir -p /app/data

# Экспонируем порты:
# 8766 - IKKF API
# 8767 - IKKF Web UI
# 8768 - Agent Dashboard
EXPOSE 8766 8767 8768

# Запуск всей системы через run-all.sh
CMD ["bash", "run-all.sh"]
