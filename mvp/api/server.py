"""
AI Network — API Gateway
OpenAI-compatible API endpoints
"""

import asyncio
import uuid
import time
import json
from typing import Optional, List
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

app = FastAPI(title="AI Network API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SCHEDULER_URL = "http://localhost:8001"

# ============================================================
# SCHEMAS
# ============================================================

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: str = "gpt-3.5-turbo"
    messages: List[ChatMessage]
    temperature: float = 0.7
    max_tokens: int = 1024

class ImageRequest(BaseModel):
    prompt: str
    n: int = 1
    size: str = "512x512"

# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/")
def root():
    return {"status": "AI Network API running", "version": "1.0.0"}

@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [
            {"id": "gpt-3.5-turbo", "object": "model", "owned_by": "ai-network"},
            {"id": "dall-e-3", "object": "model", "owned_by": "ai-network"},
            {"id": "whisper-1", "object": "model", "owned_by": "ai-network"},
        ]
    }

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    """Chat completion — OpenAI compatible"""

    task_id = str(uuid.uuid4())

    # Build prompt
    prompt = "\n".join([f"{m.role}: {m.content}" for m in request.messages])

    # Send to scheduler
    task = {
        "id": task_id,
        "type": "text",
        "payload": {
            "prompt": prompt,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
    }

    result = await send_task_and_wait(task)

    return {
        "id": f"chatcmpl-{task_id[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": result},
            "finish_reason": "stop"
        }],
        "usage": {"prompt_tokens": len(prompt.split()), "completion_tokens": len(result.split()), "total_tokens": len(prompt.split()) + len(result.split())}
    }

@app.post("/v1/images/generations")
async def generate_image(request: ImageRequest):
    """Image generation — DALL-E compatible"""

    task_id = str(uuid.uuid4())

    # Parse size
    try:
        width, height = map(int, request.size.split("x"))
    except:
        width, height = 512, 512

    task = {
        "id": task_id,
        "type": "image",
        "payload": {
            "prompt": request.prompt,
            "width": width,
            "height": height,
            "n": request.n,
        }
    }

    result = await send_task_and_wait(task, timeout=120)

    # Result should be base64 or URL
    return {
        "created": int(time.time()),
        "data": [{"url": result, "revised_prompt": request.prompt}]
    }

@app.post("/v1/audio/transcriptions")
async def transcribe_audio(
    file: UploadFile = File(...),
    model: str = Form(default="whisper-1"),
    language: str = Form(default="en"),
):
    """Audio transcription — Whisper compatible"""

    task_id = str(uuid.uuid4())

    # Read audio file
    import base64
    audio_bytes = await file.read()
    audio_b64 = base64.b64encode(audio_bytes).decode()

    task = {
        "id": task_id,
        "type": "audio",
        "payload": {
            "audio_base64": audio_b64,
            "language": language,
            "filename": file.filename,
        }
    }

    result = await send_task_and_wait(task, timeout=120)

    return {"text": result}

# ============================================================
# SCHEDULER COMMUNICATION
# ============================================================

async def send_task_and_wait(task: dict, timeout: int = 60) -> str:
    """Send task to scheduler and wait for result"""

    async with httpx.AsyncClient() as client:
        # Submit task
        try:
            resp = await client.post(f"{SCHEDULER_URL}/tasks/submit", json=task, timeout=10)
            resp.raise_for_status()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Scheduler unavailable: {e}")

        # Poll for result
        task_id = task["id"]
        start = time.time()

        while time.time() - start < timeout:
            try:
                resp = await client.get(f"{SCHEDULER_URL}/tasks/{task_id}/result", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "completed":
                        return data.get("result", "")
                    elif data.get("status") == "failed":
                        raise HTTPException(status_code=500, detail=data.get("error", "Task failed"))
            except httpx.RequestError:
                pass

            await asyncio.sleep(0.5)

        raise HTTPException(status_code=504, detail="Task timeout")

# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
