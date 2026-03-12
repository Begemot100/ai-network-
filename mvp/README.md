# AI Network MVP

Minimal working prototype of a decentralized AI inference network.

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Client    │────▶│ API Gateway │────▶│  Scheduler  │
│ (OpenAI SDK)│     │   :8000     │     │    :8001    │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                         ┌─────────────────────┼─────────────────────┐
                         │                     │                     │
                    ┌────▼────┐          ┌────▼────┐          ┌────▼────┐
                    │ Worker 1│          │ Worker 2│          │ Worker N│
                    │  (GPU)  │          │  (GPU)  │          │  (GPU)  │
                    └─────────┘          └─────────┘          └─────────┘
```

## Quick Start

### 1. Install dependencies

```bash
cd mvp
pip install -r requirements.txt
```

### 2. Start the scheduler

```bash
python scheduler/scheduler.py
# Running on http://localhost:8001
```

### 3. Start the API gateway

```bash
python api/server.py
# Running on http://localhost:8000
```

### 4. Start a worker

```bash
python worker/worker.py
# Connects to scheduler and waits for tasks
```

### 5. Send a request

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed"
)

response = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[{"role": "user", "content": "Hello!"}]
)

print(response.choices[0].message.content)
```

## Docker

```bash
docker-compose up -d
```

This starts:
- API Gateway on port 8000
- Scheduler on port 8001
- 2 worker replicas

## API Endpoints

### Chat Completion
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-3.5-turbo", "messages": [{"role": "user", "content": "Hello!"}]}'
```

### Image Generation
```bash
curl -X POST http://localhost:8000/v1/images/generations \
  -H "Content-Type: application/json" \
  -d '{"prompt": "a cat in space", "size": "512x512"}'
```

### Audio Transcription
```bash
curl -X POST http://localhost:8000/v1/audio/transcriptions \
  -F "file=@audio.mp3" \
  -F "language=en"
```

## Running with Real Models

Set environment variable to use real AI models:

```bash
USE_REAL_MODEL=true python worker/worker.py
```

Required packages for real models:
```bash
pip install torch transformers diffusers accelerate librosa
```

## Monitoring

### Scheduler stats
```bash
curl http://localhost:8001/stats
```

### List workers
```bash
curl http://localhost:8001/workers
```

## File Structure

```
mvp/
├── api/
│   └── server.py       # API Gateway (OpenAI compatible)
├── scheduler/
│   └── scheduler.py    # Task scheduler
├── worker/
│   └── worker.py       # GPU worker node
├── models/
│   ├── text.py         # Text generation
│   ├── image.py        # Image generation (Stable Diffusion)
│   └── audio.py        # Audio transcription (Whisper)
├── client_example.py   # Example client code
├── docker-compose.yml  # Docker deployment
├── Dockerfile
├── requirements.txt
└── README.md
```

## How It Works

1. **Client** sends OpenAI-compatible request to API Gateway
2. **API Gateway** creates task and sends to Scheduler
3. **Scheduler** queues task and waits for available worker
4. **Worker** polls scheduler, gets task, runs inference
5. **Worker** sends result back to scheduler
6. **API Gateway** polls scheduler for result
7. **Client** receives response

## License

MIT
