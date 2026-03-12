FROM python:3.11-slim

WORKDIR /app

# --- системные зависимости для confluent_kafka ---
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    librdkafka-dev \
    && rm -rf /var/lib/apt/lists/*

# --- копируем корневой requirements.txt ---
COPY ../../requirements.txt /app/requirements.txt

# --- устанавливаем зависимости ---
RUN pip install --no-cache-dir -r requirements.txt

# --- копируем только код микросервиса ---
COPY . /app/services/task

# копируем общий модуль common (важно!)
COPY ../../common /app/common

ENV PYTHONPATH=/app

CMD ["python", "-m", "services.task.main"]
