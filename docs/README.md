# Distributed AI Network - Documentation

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose
- PostgreSQL 15+
- Apache Kafka

### Installation

```bash
# Clone repository
git clone https://github.com/your-repo/ai-network.git
cd ai-network

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Start infrastructure
docker-compose up -d postgres kafka redis

# Run migrations
alembic upgrade head

# Start server
uvicorn server.main:app --host 0.0.0.0 --port 8050
```

### Run Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Frontend Dashboard (Vue.js)                  │
│                          Port 3000                               │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                        ┌──────▼──────┐
                        │ Main Server │
                        │ (FastAPI)   │
                        │ Port 8050   │
                        └──────┬──────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
    ┌─────▼─────┐        ┌─────▼─────┐       ┌─────▼─────┐
    │ PostgreSQL│        │   Kafka   │       │   Redis   │
    │  (5433)   │        │  (9092)   │       │  (6379)   │
    └───────────┘        └─────┬─────┘       └───────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
    ┌─────▼─────┐        ┌─────▼─────┐       ┌─────▼─────┐
    │CPU Worker │        │GPU Worker │       │ DLQ       │
    │           │        │(SD,Whisper│       │ Monitor   │
    └───────────┘        └───────────┘       └───────────┘
```

---

## API Reference

### Authentication

#### Register Worker
```bash
POST /auth/worker/register
{
    "name": "Worker-1",
    "power": 10,
    "capabilities": "text,llm,gpu"
}

Response:
{
    "worker_id": 1,
    "api_key": "sk-xxx...",
    "token": "eyJ..."
}
```

#### Get Token
```bash
POST /auth/worker/token
{
    "worker_id": 1,
    "api_key": "sk-xxx..."
}
```

#### Admin Login
```bash
POST /auth/admin/login
{
    "username": "admin",
    "password": "admin123"
}
```

### Tasks

#### Create Task
```bash
POST /tasks/create
{
    "prompt": "reverse:hello",
    "task_type": "reverse",
    "priority": 0
}
```

#### Get Next Task
```bash
GET /tasks/next/{worker_id}
```

#### Submit Result
```bash
POST /tasks/submit
{
    "task_id": 1,
    "worker_id": 1,
    "result": "olleh"
}
```

#### Validate Result
```bash
POST /tasks/validate
{
    "task_id": 1,
    "worker_id": 2,
    "result": "olleh"
}
```

### OpenAI Compatible API

#### Chat Completions
```bash
POST /v1/chat/completions
{
    "model": "gpt-3.5-turbo",
    "messages": [
        {"role": "user", "content": "Hello!"}
    ],
    "temperature": 0.7
}
```

#### Image Generation
```bash
POST /v1/images/generations
{
    "prompt": "a cat in space",
    "n": 1,
    "size": "512x512"
}
```

#### Audio Transcription
```bash
POST /v1/audio/transcriptions
Content-Type: multipart/form-data

file: <audio file>
language: en
```

#### Embeddings
```bash
POST /v1/embeddings
{
    "input": "Your text here",
    "model": "text-embedding-ada-002"
}
```

---

## Worker Setup

### CPU Worker

```bash
cd services/cpu_worker
pip install -r requirements.txt
python worker.py
```

Environment variables:
- `KAFKA_BOOTSTRAP`: Kafka address (default: kafka:9092)
- `WORKER_ID`: Unique worker ID

### GPU Worker

```bash
cd services/gpu_worker
pip install -r requirements.txt
python worker.py
```

Environment variables:
- `KAFKA_BOOTSTRAP`: Kafka address
- `WORKER_ID`: Unique worker ID
- `SD_MODEL`: Stable Diffusion model (default: stabilityai/stable-diffusion-2-1)
- `WHISPER_MODEL`: Whisper model (default: openai/whisper-base)
- `LLM_MODEL`: LLM model (default: microsoft/phi-2)

Supported task types:
- `sentiment_analysis`
- `embeddings`
- `text_generation`
- `translation`
- `summarization`
- `image_classification`
- `zero_shot_classification`
- `image_generation` (Stable Diffusion)
- `transcription` (Whisper)

---

## Two-Tier Validation

### Flow

1. **Task Created** → Status: `pending`
2. **Worker A Takes Task** → Status: `assigned`
3. **Worker A Submits** → Status: `submitted_A`
4. **Worker B Validates** → Status: `validating`
5. **Match** → Both rewarded, reputation increases
6. **Mismatch** → Worker A penalized, Worker B gets bonus

### Golden Tasks

10% of tasks are "golden tasks" with known correct answers:
- Pass: Normal reward
- Fail: Severe reputation penalty + possible ban

### Rewards by Task Type

| Type | Reward |
|------|--------|
| text | 0.05 |
| reverse | 0.10 |
| math | 0.15 |
| sentiment | 0.05 |
| llm | 0.50 |
| heavy | 1.00 |
| image_generation | 2.00 |
| transcription | 1.00 |

---

## Reputation System

### Levels

| Level | Threshold | Decay Rate |
|-------|-----------|------------|
| Bronze | 0.0 - 1.49 | 0.02/day |
| Silver | 1.5 - 1.99 | 0.015/day |
| Gold | 2.0 - 2.99 | 0.01/day |
| Platinum | 3.0 - 4.99 | 0.005/day |
| Diamond | 5.0+ | 0.002/day |

### Changes

- Successful task: +0.1
- Failed task: -0.2
- Validator bonus: +0.05
- Golden task fail: -1.0

---

## Monitoring

### Prometheus Metrics

```bash
GET /metrics/prometheus
```

Available metrics:
- `ai_network_workers_total{status}`
- `ai_network_tasks_total{status,task_type}`
- `ai_network_tasks_completed_total{task_type}`
- `ai_network_http_request_duration_seconds`

### Health Check

```bash
GET /health

Response:
{
    "status": "healthy",
    "database": true,
    "uptime_seconds": 3600,
    "version": "1.0.0"
}
```

---

## Configuration

### Environment Variables

```bash
# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
POSTGRES_USER=ai
POSTGRES_PASSWORD=secure_password
POSTGRES_DB=ainetwork

# Kafka
KAFKA_BOOTSTRAP=localhost:29092

# JWT
JWT_SECRET=your-secret-key
JWT_EXPIRY_MINUTES=15
JWT_REFRESH_EXPIRY_DAYS=7

# Features
FEATURE_GOLDEN_TASKS=true
FEATURE_REPUTATION_DECAY=true
FEATURE_COLLUSION_DETECTION=true

# Logging
LOG_LEVEL=INFO
```

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=server --cov-report=html

# Run specific test
pytest tests/test_validation.py -v
```

---

## Docker Deployment

```bash
# Build and run all services
docker-compose up -d

# View logs
docker-compose logs -f server

# Scale workers
docker-compose up -d --scale cpu-worker=3 --scale gpu-worker=2
```

---

## Troubleshooting

### Port Already in Use

```bash
# Find process
lsof -i:8050

# Kill process
kill -9 <PID>
```

### Kafka Connection Issues

```bash
# Check Kafka status
docker-compose ps kafka

# Restart Kafka
docker-compose restart kafka
```

### Database Migration Issues

```bash
# Reset migrations
alembic downgrade base
alembic upgrade head

# Mark current as head
alembic stamp head
```
