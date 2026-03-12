FROM python:3.11-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install \
    --no-cache-dir \
    --default-timeout=300 \
    -r requirements.txt

# Copy server code as package
COPY server/ ./server/

# Run as module to support relative imports
CMD ["python", "-m", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8020"]
