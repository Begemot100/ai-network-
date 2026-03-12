# AI Network — Decentralized AI Computing

[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-%E2%9D%A4-red)](https://github.com/sponsors/YOUR_USERNAME)
[![Early Access](https://img.shields.io/badge/Early%20Access-3x%20Bonus-brightgreen)](https://ai-network.io/early-access)
[![Discord](https://img.shields.io/badge/Discord-Join%20Community-7289da)](https://discord.gg/YOUR_SERVER)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Earn with your GPU** or **get cheap AI APIs**. Open source, decentralized, community-driven.

```
GPU Owners: $50-300/month passive income
Developers: 70% cheaper than OpenAI
```

🚀 **[Get Early Access (3x bonus credits)](https://ai-network.io/early-access)** | 📖 **[Documentation](docs/README.md)** | 💬 **[Discord](https://discord.gg/YOUR_SERVER)**

---

A production-grade distributed computing platform with a two-tier validation system for managing distributed AI tasks across worker nodes.

## Overview

This system coordinates task execution, validates results through a dual-worker consensus mechanism, manages reputation scores, and handles financial transactions for AI/ML workloads.

### Key Features

- **Two-Tier Validation**: Worker A executes tasks, Worker B validates results
- **Reputation System**: Bronze → Silver → Gold → Platinum → Diamond tiers
- **Economic System**: Balance tracking, rewards, penalties, and withdrawals
- **GPU & CPU Workers**: Distributed processing with AI model support
- **Kafka Event Pipeline**: Real-time task routing and result aggregation
- **Collusion Detection**: Automated detection of fraudulent worker behavior
- **JWT Authentication**: Secure API and worker authentication
- **Prometheus Metrics**: Full observability with Grafana dashboards
- **WebSocket Notifications**: Real-time status updates

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Frontend Dashboard (Vue.js)                  │
│                          Port 3000                               │
└──────────────────────────────┬──────────────────────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
    ┌─────▼─────┐      ┌──────▼──────┐     ┌──────▼──────┐
    │ Main Server│      │ API Gateway  │     │ WebSocket   │
    │ (8020)     │      │ (8000)       │     │ Server      │
    └─────┬─────┘      └──────┬───────┘     └─────────────┘
          │                   │
          └───────────────────┼─────────────────┐
                              │                 │
                        ┌─────▼─────┐          │
                        │   Kafka   │◄─────────┘
                        │  (9092)   │
                        └─┬──────┬──┘
                          │      │
          ┌───────────────┼──────┼────────────┐
          │               │      │            │
    ┌─────▼──┐      ┌────▼──┐  │      ┌─────▼──┐
    │ Router  │      │Reducer│  │      │  DLQ   │
    │         │      │       │  │      │Monitor │
    └────┬────┘      └───────┘  │      └────────┘
         │                       │
    ┌────┴───┬──────────┐       │
    │        │          │       │
┌───▼──┐ ┌──▼───┐  ┌───▼──┐    │
│ CPU  │ │ GPU  │  │Other │◄───┘
│Worker│ │Worker│  │Workers│
└──────┘ └──────┘  └───────┘
    │       │          │
    └───────┴──────────┘
         │
    ┌────▼─────┐
    │PostgreSQL│
    │  Redis   │
    └──────────┘
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+
- PostgreSQL 15+
- Apache Kafka

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd my-ai-network
```

2. Copy environment file:
```bash
cp .env.example .env
```

3. Start services:
```bash
docker-compose up -d
```

4. Initialize database:
```bash
# Run Alembic migrations
alembic upgrade head
```

5. Access the dashboard:
- Frontend: http://localhost:3000
- API: http://localhost:8020
- Kafka UI: http://localhost:8080

## Project Structure

```
my-ai-network/
├── server/                     # Main FastAPI server
│   ├── main.py                 # Application entry point
│   ├── config.py               # Settings & configuration
│   ├── models.py               # SQLModel database models
│   ├── schemas.py              # Pydantic request/response schemas
│   ├── db.py                   # Database connection management
│   ├── auth.py                 # JWT authentication
│   ├── collusion.py            # Collusion detection system
│   ├── reputation_decay.py     # Reputation decay logic
│   ├── metrics.py              # Prometheus metrics
│   ├── ws.py                   # WebSocket handlers
│   └── routers/
│       ├── auth.py             # Authentication endpoints
│       ├── workers.py          # Worker management
│       ├── tasks.py            # Task & validation logic
│       ├── admin_panel.py      # Admin endpoints
│       └── wallet.py           # Financial operations
├── services/
│   ├── api/                    # API Gateway service
│   ├── router/                 # Kafka task router
│   ├── cpu_worker/             # CPU worker implementation
│   ├── gpu_worker/             # GPU worker implementation
│   ├── reducer/                # Result aggregator
│   └── dlq_monitor/            # Dead Letter Queue monitor
├── frontend/                   # Vue.js dashboard
├── alembic/                    # Database migrations
├── monitoring/                 # Prometheus & Grafana configs
├── tests/                      # Test suite
├── init-db/                    # Database schema
├── docker-compose.yml          # Service orchestration
└── requirements.txt            # Python dependencies
```

## API Documentation

### Authentication

```bash
# Register worker with authentication
POST /auth/worker/register
{
    "name": "Worker-1",
    "power": 10,
    "capabilities": "text,llm"
}

# Authenticate worker
POST /auth/worker/token
{
    "worker_id": 1,
    "api_key": "your-api-key"
}

# Admin login
POST /auth/admin/login
{
    "username": "admin",
    "password": "admin123"
}
```

### Tasks

```bash
# Create task
POST /tasks/create
{
    "prompt": "reverse:hello",
    "task_type": "reverse",
    "priority": 0
}

# Get next task (Worker A)
GET /tasks/next/{worker_id}

# Submit result
POST /tasks/submit
{
    "task_id": 1,
    "worker_id": 1,
    "result": "olleh"
}

# Validate (Worker B)
POST /tasks/validate
{
    "task_id": 1,
    "worker_id": 2,
    "result": "olleh"
}
```

### Workers

```bash
# Register worker
POST /workers/register
{
    "name": "Worker-1",
    "power": 10
}

# Get worker info
GET /workers/{worker_id}

# Worker heartbeat
POST /workers/heartbeat?worker_id=1

# List workers
GET /workers/?page=1&page_size=20
```

### Admin

```bash
# Dashboard stats
GET /admin/dashboard

# Ban worker
POST /admin/ban
{
    "worker_id": 1,
    "reason": "Fraudulent behavior"
}

# Collusion scan
GET /admin/collusion/scan?days=30

# Run reputation decay
POST /admin/reputation-decay/run?dry_run=true
```

## Task Types & Rewards

| Task Type | Reward | Description |
|-----------|--------|-------------|
| text | 0.05 | Basic text processing |
| reverse | 0.10 | String reversal |
| math | 0.15 | Mathematical computation |
| sentiment | 0.05 | Sentiment analysis |
| llm | 0.50 | LLM inference |
| heavy | 1.00 | Heavy computation |

## Reputation System

| Level | Threshold | Decay Rate |
|-------|-----------|------------|
| Bronze | 0.0 - 1.49 | 0.02/day |
| Silver | 1.5 - 1.99 | 0.015/day |
| Gold | 2.0 - 2.99 | 0.01/day |
| Platinum | 3.0 - 4.99 | 0.005/day |
| Diamond | 5.0+ | 0.002/day |

## Two-Tier Validation Flow

1. **Task Created**: New task enters `pending` queue
2. **Worker A Assigned**: Task status → `assigned`
3. **Worker A Submits**: Task status → `submitted_A`
4. **Worker B Validates**: Task status → `validating`
5. **Results Match**: Both workers rewarded, reputation +
6. **Results Mismatch**: Worker A penalized, Worker B bonus

### Golden Tasks (Honeypots)

- 10% of tasks are "golden tasks" with known correct answers
- Failing a golden task results in severe reputation penalty
- Helps detect malicious or lazy workers

## Configuration

Key environment variables (see `.env.example`):

```bash
# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
POSTGRES_USER=ai
POSTGRES_PASSWORD=ai_secure_password
POSTGRES_DB=ainetwork

# Kafka
KAFKA_BOOTSTRAP=localhost:29092

# JWT
JWT_SECRET=change-me-in-production
JWT_EXPIRY_MINUTES=15

# Feature Flags
FEATURE_GOLDEN_TASKS=true
FEATURE_REPUTATION_DECAY=true
FEATURE_COLLUSION_DETECTION=true
```

## Monitoring

### Prometheus Metrics

Available at `GET /metrics/prometheus`:

- `ai_network_workers_total` - Worker counts by status
- `ai_network_tasks_queue_size` - Task queue depths
- `ai_network_tasks_completed_total` - Completed tasks counter
- `ai_network_http_request_duration_seconds` - Request latencies

### Grafana Dashboard

Import `monitoring/grafana-dashboard.json` for pre-built dashboards.

## Testing

```bash
# Install test dependencies
pip install -r requirements-test.txt

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=server --cov-report=html
```

## Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## WebSocket Events

Connect to `/ws` for real-time updates:

```javascript
const ws = new WebSocket('ws://localhost:8020/ws');

ws.onopen = () => {
    // Subscribe to task updates
    ws.send(JSON.stringify({action: 'subscribe', room: 'tasks'}));
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Event:', data.type, data.data);
};
```

## Sponsors

Support AI Network development:

- **[GitHub Sponsors](https://github.com/sponsors/YOUR_USERNAME)** — Monthly support
- **[Early Access](https://ai-network.io/early-access)** — Get 3-4x bonus API credits
- **[Open Collective](https://opencollective.com/ai-network)** — Transparent funding

### Founding Members

<!-- sponsors -->
*Be the first sponsor!*
<!-- sponsors -->

## License

MIT License — use it however you want.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

---

**Made with ❤️ by the AI Network community**

[Website](https://ai-network.io) • [GitHub](https://github.com/YOUR_REPO) • [Discord](https://discord.gg/YOUR_SERVER) • [Twitter](https://twitter.com/ainetwork)
