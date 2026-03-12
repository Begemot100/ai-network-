"""
Simple Task Worker - processes tasks directly from database.
No Kafka required. Good for demo/development.
"""

import os
import sys
import time
import json
import logging
import random
import string

# Add parent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from sqlmodel import Session, select, create_engine
from server.models import Task

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Database connection
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://ai:ai_secure_password@localhost:5433/ainetwork"
)
engine = create_engine(DATABASE_URL)

# Simulated processing functions
def process_chat(payload: dict, task_prompt: str = "") -> str:
    """Simulate chat response."""
    prompts = payload.get("prompts", [task_prompt])
    prompt = prompts[0] if prompts else task_prompt

    # Simple responses based on input
    prompt_lower = prompt.lower()
    if "hello" in prompt_lower or "hi" in prompt_lower:
        return "Hello! I'm an AI assistant from AI Network. How can I help you today?"
    elif "2+2" in prompt_lower or "2 + 2" in prompt_lower:
        return "2 + 2 = 4"
    elif "weather" in prompt_lower:
        return "I don't have access to real-time weather data, but I hope it's nice where you are!"
    elif "who are you" in prompt_lower:
        return "I'm an AI assistant running on the decentralized AI Network. I help with various tasks like chat, image generation, and audio transcription."
    else:
        return f"I received your message. This is a demo response from the AI Network. Your input was: {prompt[:100]}..."


def process_image(payload: dict) -> dict:
    """Simulate image generation - return a placeholder."""
    prompt = payload.get("prompt", "")
    width = payload.get("width", 512)
    height = payload.get("height", 512)

    # Return a placeholder image URL (using placeholder service)
    # In production, this would be actual Stable Diffusion output
    return {
        "status": "completed",
        "images": [
            {
                "url": f"https://placehold.co/{width}x{height}/1a1a2e/10b981?text=AI+Network",
                "prompt": prompt,
                "width": width,
                "height": height,
            }
        ],
        "message": f"Demo image for: {prompt}"
    }


def process_transcription(payload: dict) -> dict:
    """Simulate transcription."""
    filename = payload.get("filename", "audio.mp3")
    language = payload.get("language", "en")

    return {
        "status": "completed",
        "text": f"[Demo transcription] This is a simulated transcription of {filename}. In production, Whisper would process your audio file and return the actual text.",
        "language": language,
    }


def process_embeddings(payload: dict) -> dict:
    """Generate simple embeddings (random for demo)."""
    texts = payload.get("texts", [])

    # Generate random embeddings (384 dimensions like MiniLM)
    embeddings = []
    for text in texts:
        # Use hash for reproducibility
        random.seed(hash(text) % (2**32))
        emb = [random.gauss(0, 0.1) for _ in range(384)]
        embeddings.append(emb)

    return {
        "status": "completed",
        "embeddings": embeddings,
        "model": "sentence-transformers/all-MiniLM-L6-v2",
    }


def process_task(task: Task) -> str:
    """Process a task based on its type."""
    # Get payload - handle case where attribute might not exist
    payload = getattr(task, 'payload', None) or {}
    task_type = payload.get("type", task.task_type) if payload else task.task_type

    logger.info(f"Processing task #{task.id} type={task_type}")

    if task_type in ["text_generation", "llm", "chat"]:
        return process_chat(payload, task.prompt)
    elif task_type == "image_generation":
        return json.dumps(process_image(payload))
    elif task_type == "transcription":
        return json.dumps(process_transcription(payload))
    elif task_type == "embeddings":
        return json.dumps(process_embeddings(payload))
    elif task_type == "reverse":
        # Simple reverse task
        text = task.prompt.replace("reverse:", "").strip()
        return text[::-1]
    elif task_type == "sentiment":
        return json.dumps({"label": "POSITIVE", "score": 0.95})
    else:
        return f"Processed task type: {task_type}"


def worker_loop():
    """Main worker loop - poll database for pending tasks."""
    logger.info("Simple Worker started")
    logger.info(f"Database: {DATABASE_URL}")

    while True:
        try:
            with Session(engine) as session:
                # Get pending tasks
                tasks = session.exec(
                    select(Task)
                    .where(Task.status == "pending")
                    .order_by(Task.priority.desc(), Task.id)
                    .limit(5)
                ).all()

                for task in tasks:
                    try:
                        # Mark as processing
                        task.status = "processing"
                        session.add(task)
                        session.commit()

                        # Process
                        result = process_task(task)

                        # Mark as completed
                        task.status = "completed"
                        task.result = result
                        session.add(task)
                        session.commit()

                        logger.info(f"Task #{task.id} completed")

                    except Exception as e:
                        logger.error(f"Error processing task #{task.id}: {e}")
                        task.status = "failed"
                        task.result = str(e)
                        session.add(task)
                        session.commit()

                if not tasks:
                    # No tasks, wait a bit
                    time.sleep(1)

        except Exception as e:
            logger.error(f"Worker error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    worker_loop()
