# Worker Setup Guide

## How to Earn with Your GPU

This guide explains how to set up a worker node and start earning tokens by processing AI tasks.

---

## Requirements

### Hardware

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| GPU | GTX 1060 6GB | RTX 3080+ |
| RAM | 8 GB | 16+ GB |
| Storage | 20 GB | 50+ GB SSD |
| Internet | 10 Mbps | 100+ Mbps |

### Software

- Python 3.11+
- CUDA 11.8+ (for NVIDIA GPUs)
- Docker (optional)

---

## Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/your-repo/ai-network.git
cd ai-network/services/gpu_worker
```

### 2. Install Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt

# For CUDA support (adjust version as needed)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

### 3. Configure

Create `.env` file:

```bash
# Worker config
WORKER_ID=my-gpu-worker-001
KAFKA_BOOTSTRAP=your-kafka-server:9092

# Model selection (optional)
SD_MODEL=stabilityai/stable-diffusion-2-1
WHISPER_MODEL=openai/whisper-base
LLM_MODEL=microsoft/phi-2

# Performance
BATCH_SIZE=4
MAX_SEQ_LENGTH=512
```

### 4. Run Worker

```bash
python worker.py
```

---

## Docker Deployment

### Build Image

```bash
cd services/gpu_worker
docker build -t ai-network-gpu-worker .
```

### Run Container

```bash
docker run -d \
  --gpus all \
  --name gpu-worker \
  -e WORKER_ID=my-gpu-worker \
  -e KAFKA_BOOTSTRAP=kafka:9092 \
  ai-network-gpu-worker
```

### Docker Compose

```yaml
version: '3.8'
services:
  gpu-worker:
    build: ./services/gpu_worker
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    environment:
      - WORKER_ID=gpu-worker-1
      - KAFKA_BOOTSTRAP=kafka:9092
    restart: unless-stopped
```

---

## Supported Task Types

### Image Generation (Stable Diffusion)

- **Reward**: 2.0 tokens per image
- **GPU Memory**: 6+ GB
- **Avg Time**: 5-15 seconds

### Audio Transcription (Whisper)

- **Reward**: 1.0 tokens per minute of audio
- **GPU Memory**: 2+ GB
- **Avg Time**: Real-time to 2x

### Text Generation (LLM)

- **Reward**: 0.5 tokens per request
- **GPU Memory**: 4+ GB (model dependent)
- **Avg Time**: 1-5 seconds

### Embeddings

- **Reward**: 0.1 tokens per batch
- **GPU Memory**: 1+ GB
- **Avg Time**: < 1 second

### Sentiment Analysis

- **Reward**: 0.05 tokens per batch
- **GPU Memory**: 1+ GB
- **Avg Time**: < 1 second

---

## Performance Optimization

### Memory Management

```python
# Enable in worker config
pipe.enable_attention_slicing()
pipe.enable_xformers_memory_efficient_attention()  # Requires xformers
```

### Batch Processing

Increase batch size for better throughput:

```bash
export BATCH_SIZE=8  # Adjust based on GPU memory
```

### Model Selection

Choose appropriate models for your GPU:

| GPU VRAM | Recommended Models |
|----------|-------------------|
| 6 GB | SD 2.1, Whisper base, Phi-2 |
| 8 GB | SD 2.1, Whisper small, Phi-2 |
| 12 GB | SDXL, Whisper medium, Mistral 7B |
| 24 GB | SDXL, Whisper large, LLaMA 13B |

---

## Monitoring

### View Logs

```bash
# Direct run
python worker.py 2>&1 | tee worker.log

# Docker
docker logs -f gpu-worker
```

### Check Status

The worker sends heartbeats every 5 seconds with:
- CPU/RAM usage
- GPU memory
- Loaded models
- Processing statistics

### Prometheus Metrics

Worker metrics are published to Kafka topic `ai.workers.heartbeat`.

---

## Troubleshooting

### Out of Memory

```
RuntimeError: CUDA out of memory
```

**Solution:**
1. Reduce batch size
2. Enable memory optimizations
3. Use smaller models

### Kafka Connection Failed

```
NoBrokersAvailable: Unable to connect to broker
```

**Solution:**
1. Check Kafka server is running
2. Verify `KAFKA_BOOTSTRAP` address
3. Check firewall rules

### Model Download Failed

```
HTTPError: 401 Client Error
```

**Solution:**
1. Login to HuggingFace: `huggingface-cli login`
2. Accept model license on HuggingFace website
3. Check internet connection

---

## Earnings Calculator

| Task Type | Reward | Tasks/Hour | Hourly Earnings |
|-----------|--------|------------|-----------------|
| Image Gen | 2.0 | 120 | 240 tokens |
| Transcription | 1.0 | 60 | 60 tokens |
| LLM | 0.5 | 200 | 100 tokens |
| Embeddings | 0.1 | 1000 | 100 tokens |

**Estimated monthly earnings (24/7 operation):**
- RTX 3080: ~$50-150/month
- RTX 4090: ~$150-300/month

*Actual earnings depend on network demand and task distribution.*

---

## Security Best Practices

1. **Run in isolated environment** (Docker/VM)
2. **Don't expose worker ports** to the internet
3. **Regularly update** dependencies
4. **Monitor resource usage** for anomalies
5. **Use dedicated machine** for worker operations

---

## Support

- GitHub Issues: [Link to issues]
- Discord: [Link to discord]
- Documentation: [Link to docs]
