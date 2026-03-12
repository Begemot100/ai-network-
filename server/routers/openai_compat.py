"""
OpenAI-compatible API endpoints.
Drop-in replacement for OpenAI API - just change the base URL.

Endpoints:
- POST /v1/chat/completions - Chat completions (LLM)
- POST /v1/images/generations - Image generation (Stable Diffusion)
- POST /v1/audio/transcriptions - Audio transcription (Whisper)
- GET /v1/models - List available models
"""

import base64
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Literal

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..db import get_session
from ..models import Task, Worker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["OpenAI Compatible"])


# =============================================================================
# SCHEMAS
# =============================================================================

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "gpt-3.5-turbo"
    messages: List[ChatMessage]
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=1024, ge=1, le=4096)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    stream: bool = False
    n: int = Field(default=1, ge=1, le=4)


class ChatCompletionChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str = "stop"


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: ChatCompletionUsage


class ImageGenerationRequest(BaseModel):
    prompt: str
    model: str = "dall-e-3"
    n: int = Field(default=1, ge=1, le=4)
    size: str = Field(default="1024x1024")
    quality: str = Field(default="standard")
    response_format: str = Field(default="b64_json")  # "url" or "b64_json"


class ImageData(BaseModel):
    b64_json: Optional[str] = None
    url: Optional[str] = None
    revised_prompt: Optional[str] = None


class ImageGenerationResponse(BaseModel):
    created: int
    data: List[ImageData]


class TranscriptionResponse(BaseModel):
    text: str


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str


class ModelsResponse(BaseModel):
    object: str = "list"
    data: List[ModelInfo]


# =============================================================================
# MODEL MAPPING
# =============================================================================

# Map OpenAI model names to our internal models
MODEL_MAPPING = {
    # Chat/LLM models
    "gpt-3.5-turbo": "microsoft/phi-2",
    "gpt-4": "microsoft/phi-2",
    "gpt-4-turbo": "microsoft/phi-2",
    # Image models
    "dall-e-2": "stabilityai/stable-diffusion-2-1",
    "dall-e-3": "stabilityai/stable-diffusion-2-1",
    # Audio models
    "whisper-1": "openai/whisper-base",
}

AVAILABLE_MODELS = [
    {"id": "gpt-3.5-turbo", "owned_by": "ai-network", "type": "chat"},
    {"id": "gpt-4", "owned_by": "ai-network", "type": "chat"},
    {"id": "dall-e-2", "owned_by": "ai-network", "type": "image"},
    {"id": "dall-e-3", "owned_by": "ai-network", "type": "image"},
    {"id": "whisper-1", "owned_by": "ai-network", "type": "audio"},
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def parse_size(size: str) -> tuple:
    """Parse size string to width, height."""
    try:
        parts = size.lower().split("x")
        return int(parts[0]), int(parts[1])
    except:
        return 1024, 1024


def get_available_worker(session: Session) -> Optional[Worker]:
    """Get an available GPU worker."""
    worker = session.exec(
        select(Worker)
        .where(Worker.status.in_(["idle", "online"]))
        .where(Worker.is_banned == False)
        .where(Worker.capabilities.contains("gpu"))
        .order_by(Worker.reputation.desc())
        .limit(1)
    ).first()
    return worker


def wait_for_task(session: Session, task_id: int, timeout: float = 30.0) -> Optional[Task]:
    """Wait for task to complete with polling."""
    import time as time_module
    start = time_module.time()
    while time_module.time() - start < timeout:
        session.expire_all()
        task = session.get(Task, task_id)
        if task and task.status in ["completed", "failed"]:
            return task
        time_module.sleep(0.5)
    return None


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/models", response_model=ModelsResponse)
def list_models():
    """List available models."""
    now = int(time.time())
    return ModelsResponse(
        data=[
            ModelInfo(
                id=m["id"],
                created=now - 86400,  # Created "yesterday"
                owned_by=m["owned_by"]
            )
            for m in AVAILABLE_MODELS
        ]
    )


@router.get("/models/{model_id}")
def get_model(model_id: str):
    """Get model info."""
    for m in AVAILABLE_MODELS:
        if m["id"] == model_id:
            return ModelInfo(
                id=m["id"],
                created=int(time.time()) - 86400,
                owned_by=m["owned_by"]
            )
    raise HTTPException(status_code=404, detail=f"Model {model_id} not found")


@router.post("/chat/completions", response_model=ChatCompletionResponse)
def chat_completions(
    request: ChatCompletionRequest,
    session: Session = Depends(get_session),
):
    """
    Chat completions endpoint (OpenAI compatible).

    Creates a task and returns simulated response.
    In production, this would wait for worker to process.
    """
    # Build prompt from messages
    prompt_parts = []
    for msg in request.messages:
        if msg.role == "system":
            prompt_parts.append(f"System: {msg.content}")
        elif msg.role == "user":
            prompt_parts.append(f"User: {msg.content}")
        elif msg.role == "assistant":
            prompt_parts.append(f"Assistant: {msg.content}")

    full_prompt = "\n".join(prompt_parts) + "\nAssistant:"

    # Create task in database
    task = Task(
        prompt=full_prompt,
        task_type="llm",
        priority=0,
        status="pending",
        payload={
            "type": "text_generation",
            "prompts": [full_prompt],
            "max_length": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "model": MODEL_MAPPING.get(request.model, request.model),
        }
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    # Wait for worker to process (sync mode)
    completed_task = wait_for_task(session, task.id, timeout=30.0)

    if completed_task and completed_task.status == "completed":
        response_text = completed_task.result or "No response generated."
    else:
        response_text = f"[Task #{task.id} is still processing. Check back later.]"

    # Estimate tokens
    prompt_tokens = len(full_prompt.split())
    completion_tokens = len(response_text.split())

    return ChatCompletionResponse(
        id=f"chatcmpl-{task.uuid}",
        created=int(time.time()),
        model=request.model,
        choices=[
            ChatCompletionChoice(
                index=i,
                message=ChatMessage(
                    role="assistant",
                    content=response_text
                ),
                finish_reason="stop"
            )
            for i in range(request.n)
        ],
        usage=ChatCompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens
        )
    )


@router.post("/images/generations", response_model=ImageGenerationResponse)
def generate_images(
    request: ImageGenerationRequest,
    session: Session = Depends(get_session),
):
    """
    Image generation endpoint (OpenAI DALL-E compatible).

    Creates image generation task.
    """
    width, height = parse_size(request.size)

    # Map quality to steps
    steps = 25 if request.quality == "standard" else 40

    # Create task
    task = Task(
        prompt=request.prompt,
        task_type="image_generation",
        priority=0,
        status="pending",
        payload={
            "type": "image_generation",
            "prompt": request.prompt,
            "negative_prompt": "blurry, bad quality, distorted",
            "width": width,
            "height": height,
            "num_images": request.n,
            "steps": steps,
            "guidance_scale": 7.5,
            "model": MODEL_MAPPING.get(request.model, request.model),
        }
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    # Wait for worker to process
    completed_task = wait_for_task(session, task.id, timeout=60.0)

    if completed_task and completed_task.status == "completed" and completed_task.result:
        try:
            result_data = json.loads(completed_task.result)
            images = result_data.get("images", [])
            return ImageGenerationResponse(
                created=int(time.time()),
                data=[
                    ImageData(
                        b64_json=img.get("b64_json"),
                        url=img.get("url"),
                        revised_prompt=request.prompt
                    )
                    for img in images
                ]
            )
        except json.JSONDecodeError:
            pass

    # Fallback
    return ImageGenerationResponse(
        created=int(time.time()),
        data=[
            ImageData(
                b64_json=None,
                url=f"/api/tasks/{task.id}/result",
                revised_prompt=request.prompt
            )
            for _ in range(request.n)
        ]
    )


@router.post("/audio/transcriptions", response_model=TranscriptionResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    model: str = Form(default="whisper-1"),
    language: Optional[str] = Form(default=None),
    response_format: str = Form(default="json"),
    session: Session = Depends(get_session),
):
    """
    Audio transcription endpoint (OpenAI Whisper compatible).
    """
    # Read audio file
    audio_content = await file.read()
    audio_base64 = base64.b64encode(audio_content).decode()

    # Create task
    task = Task(
        prompt=f"Transcribe: {file.filename}",
        task_type="transcription",
        priority=0,
        status="pending",
        payload={
            "type": "transcription",
            "audio_base64": audio_base64,
            "language": language or "en",
            "task": "transcribe",
            "filename": file.filename,
            "model": MODEL_MAPPING.get(model, model),
        }
    )
    session.add(task)
    session.commit()

    # Return placeholder
    return TranscriptionResponse(
        text=f"[Task #{task.id} created. Transcription will be processed by GPU worker.]"
    )


@router.post("/audio/translations", response_model=TranscriptionResponse)
async def translate_audio(
    file: UploadFile = File(...),
    model: str = Form(default="whisper-1"),
    response_format: str = Form(default="json"),
    session: Session = Depends(get_session),
):
    """
    Audio translation endpoint (translate to English).
    """
    audio_content = await file.read()
    audio_base64 = base64.b64encode(audio_content).decode()

    task = Task(
        prompt=f"Translate: {file.filename}",
        task_type="transcription",
        priority=0,
        status="pending",
        payload={
            "type": "transcription",
            "audio_base64": audio_base64,
            "task": "translate",  # Whisper will translate to English
            "filename": file.filename,
            "model": MODEL_MAPPING.get(model, model),
        }
    )
    session.add(task)
    session.commit()

    return TranscriptionResponse(
        text=f"[Task #{task.id} created. Translation will be processed by GPU worker.]"
    )


# =============================================================================
# EMBEDDINGS (bonus)
# =============================================================================

class EmbeddingRequest(BaseModel):
    input: str | List[str]
    model: str = "text-embedding-ada-002"


class EmbeddingData(BaseModel):
    object: str = "embedding"
    index: int
    embedding: List[float]


class EmbeddingResponse(BaseModel):
    object: str = "list"
    model: str
    data: List[EmbeddingData]
    usage: dict


@router.post("/embeddings", response_model=EmbeddingResponse)
def create_embeddings(
    request: EmbeddingRequest,
    session: Session = Depends(get_session),
):
    """
    Embeddings endpoint (OpenAI compatible).
    """
    texts = request.input if isinstance(request.input, list) else [request.input]

    task = Task(
        prompt=f"Embeddings for {len(texts)} texts",
        task_type="embeddings",
        priority=0,
        status="pending",
        payload={
            "type": "embeddings",
            "texts": texts,
        }
    )
    session.add(task)
    session.commit()

    # Return placeholder with dummy embeddings
    # In production: wait for actual embeddings
    dummy_embedding = [0.0] * 384  # MiniLM dimension

    return EmbeddingResponse(
        model=request.model,
        data=[
            EmbeddingData(
                index=i,
                embedding=dummy_embedding
            )
            for i in range(len(texts))
        ],
        usage={
            "prompt_tokens": sum(len(t.split()) for t in texts),
            "total_tokens": sum(len(t.split()) for t in texts)
        }
    )
