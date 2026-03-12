from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import NoBrokersAvailable
import json
import math
import os
import time
import uuid
import platform
import threading
import psutil
import re
import requests
from io import BytesIO

# =========================================================
# CONFIG
# =========================================================

WORKER_ID = str(uuid.uuid4())
BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
USE_AI_MODELS = os.getenv("USE_AI_MODELS", "true").lower() == "true"

TASK_TOPIC = os.getenv("INPUT_TOPIC", "ai.tasks.cpu")
RESULT_TOPIC = os.getenv("OUTPUT_TOPIC", "ai.results.v2")
DLQ_TOPIC = "ai.dlq"
HEARTBEAT_TOPIC = "ai.workers.heartbeat"

# Supported task types
LIMITS = {
    "task_types": [
        "prime_count",
        "sentiment_analysis",
        "translation",
        "summarization",
        "image_classification",
        "text_generation",
        "question_answering",
    ]
}

HEARTBEAT_INTERVAL = 5

print(f"[worker {WORKER_ID}] starting...", flush=True)
print(f"[worker {WORKER_ID}] AI models enabled: {USE_AI_MODELS}", flush=True)

# =========================================================
# LAZY MODEL LOADING (saves memory)
# =========================================================

_models = {}

def get_model(model_type):
    """Lazy load models only when needed."""
    global _models

    if model_type in _models:
        return _models[model_type]

    print(f"[worker {WORKER_ID}] Loading model: {model_type}...", flush=True)

    from transformers import pipeline

    if model_type == "sentiment":
        _models[model_type] = pipeline(
            "sentiment-analysis",
            model="distilbert-base-uncased-finetuned-sst-2-english"
        )

    elif model_type == "translation_en_fr":
        _models[model_type] = pipeline(
            "translation_en_to_fr",
            model="Helsinki-NLP/opus-mt-en-fr"
        )

    elif model_type == "translation_en_de":
        _models[model_type] = pipeline(
            "translation_en_to_de",
            model="Helsinki-NLP/opus-mt-en-de"
        )

    elif model_type == "translation_en_es":
        _models[model_type] = pipeline(
            "translation_en_to_es",
            model="Helsinki-NLP/opus-mt-en-es"
        )

    elif model_type == "translation_en_ru":
        _models[model_type] = pipeline(
            "translation_en_to_ru",
            model="Helsinki-NLP/opus-mt-en-ru"
        )

    elif model_type == "summarization":
        _models[model_type] = pipeline(
            "summarization",
            model="facebook/bart-large-cnn"
        )

    elif model_type == "image_classification":
        _models[model_type] = pipeline(
            "image-classification",
            model="google/vit-base-patch16-224"
        )

    elif model_type == "text_generation":
        _models[model_type] = pipeline(
            "text-generation",
            model="gpt2"
        )

    elif model_type == "question_answering":
        _models[model_type] = pipeline(
            "question-answering",
            model="distilbert-base-cased-distilled-squad"
        )

    print(f"[worker {WORKER_ID}] Model {model_type} loaded!", flush=True)
    return _models[model_type]

# =========================================================
# PRIME COUNT
# =========================================================

def is_prime(n: int) -> bool:
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    r = int(math.sqrt(n))
    for i in range(3, r + 1, 2):
        if n % i == 0:
            return False
    return True

# =========================================================
# SENTIMENT ANALYSIS
# =========================================================

# Fallback rule-based (when AI models disabled)
POSITIVE_WORDS = {
    "love", "great", "amazing", "excellent", "fantastic",
    "good", "awesome", "perfect", "fast", "happy",
    "recommend", "five", "stars", "best", "wonderful"
}

NEGATIVE_WORDS = {
    "bad", "terrible", "awful", "worst", "slow",
    "disappointed", "hate", "never", "waste",
    "poor", "broken", "refund", "horrible", "ugly"
}

WORD_RE = re.compile(r"[a-z]+")

def analyze_sentiment_simple(text: str) -> dict:
    """Rule-based sentiment (fast, no GPU needed)."""
    words = WORD_RE.findall(text.lower())
    pos = sum(1 for w in words if w in POSITIVE_WORDS)
    neg = sum(1 for w in words if w in NEGATIVE_WORDS)
    score = pos - neg

    if score > 0:
        label = "positive"
    elif score < 0:
        label = "negative"
    else:
        label = "neutral"

    return {
        "text": text,
        "label": label,
        "score": score,
        "positive_hits": pos,
        "negative_hits": neg,
    }

def analyze_sentiment_ai(text: str) -> dict:
    """AI-based sentiment using transformers."""
    classifier = get_model("sentiment")
    result = classifier(text[:512])[0]  # Limit text length

    return {
        "text": text,
        "label": result["label"].lower(),
        "score": round(result["score"], 4),
        "model": "distilbert-sst2",
    }

def analyze_sentiment(text: str) -> dict:
    """Choose between AI and rule-based."""
    if USE_AI_MODELS:
        try:
            return analyze_sentiment_ai(text)
        except Exception as e:
            print(f"AI sentiment failed, using fallback: {e}", flush=True)
            return analyze_sentiment_simple(text)
    return analyze_sentiment_simple(text)

# =========================================================
# TRANSLATION
# =========================================================

SUPPORTED_LANGUAGES = {
    "fr": "translation_en_fr",
    "de": "translation_en_de",
    "es": "translation_en_es",
    "ru": "translation_en_ru",
}

def translate_text(text: str, target_lang: str) -> dict:
    """Translate English text to target language."""
    if target_lang not in SUPPORTED_LANGUAGES:
        return {
            "error": f"Unsupported language: {target_lang}",
            "supported": list(SUPPORTED_LANGUAGES.keys()),
        }

    model_key = SUPPORTED_LANGUAGES[target_lang]
    translator = get_model(model_key)

    result = translator(text[:512])[0]

    return {
        "source_text": text,
        "translated_text": result["translation_text"],
        "source_lang": "en",
        "target_lang": target_lang,
    }

# =========================================================
# SUMMARIZATION
# =========================================================

def summarize_text(text: str, max_length: int = 130, min_length: int = 30) -> dict:
    """Summarize long text."""
    summarizer = get_model("summarization")

    # BART needs at least some text
    if len(text) < 100:
        return {
            "original_text": text,
            "summary": text,
            "note": "Text too short to summarize",
        }

    result = summarizer(
        text[:1024],
        max_length=max_length,
        min_length=min_length,
        do_sample=False
    )[0]

    return {
        "original_length": len(text),
        "summary": result["summary_text"],
        "summary_length": len(result["summary_text"]),
    }

# =========================================================
# IMAGE CLASSIFICATION
# =========================================================

def classify_image(image_url: str) -> dict:
    """Classify image from URL."""
    from PIL import Image

    classifier = get_model("image_classification")

    # Download image
    response = requests.get(image_url, timeout=30)
    response.raise_for_status()
    image = Image.open(BytesIO(response.content))

    # Classify
    results = classifier(image)

    return {
        "image_url": image_url,
        "predictions": [
            {"label": r["label"], "score": round(r["score"], 4)}
            for r in results[:5]  # Top 5
        ],
    }

# =========================================================
# TEXT GENERATION
# =========================================================

def generate_text(prompt: str, max_length: int = 100) -> dict:
    """Generate text continuation."""
    generator = get_model("text_generation")

    result = generator(
        prompt,
        max_length=max_length,
        num_return_sequences=1,
        do_sample=True,
        temperature=0.7,
    )[0]

    return {
        "prompt": prompt,
        "generated_text": result["generated_text"],
    }

# =========================================================
# QUESTION ANSWERING
# =========================================================

def answer_question(question: str, context: str) -> dict:
    """Answer question based on context."""
    qa = get_model("question_answering")

    result = qa(question=question, context=context[:1000])

    return {
        "question": question,
        "answer": result["answer"],
        "confidence": round(result["score"], 4),
        "start": result["start"],
        "end": result["end"],
    }

# =========================================================
# KAFKA PRODUCER
# =========================================================

while True:
    try:
        producer = KafkaProducer(
            bootstrap_servers=BOOTSTRAP,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        break
    except NoBrokersAvailable:
        print("Kafka not ready, retry in 2s", flush=True)
        time.sleep(2)

print("Kafka connected", flush=True)

# =========================================================
# HEARTBEAT
# =========================================================

def heartbeat_loop():
    while True:
        try:
            producer.send(HEARTBEAT_TOPIC, {
                "worker_id": WORKER_ID,
                "cpu_percent": psutil.cpu_percent(),
                "ram_mb": psutil.virtual_memory().used // 1024 // 1024,
                "ts": int(time.time()),
                "ai_enabled": USE_AI_MODELS,
                "loaded_models": list(_models.keys()),
                "system": {
                    "os": platform.system(),
                    "arch": platform.machine(),
                    "python": platform.python_version(),
                },
            })
            producer.flush()
        except Exception as e:
            print("Heartbeat error:", e, flush=True)

        time.sleep(HEARTBEAT_INTERVAL)

threading.Thread(target=heartbeat_loop, daemon=True).start()
print("Heartbeat started", flush=True)

# =========================================================
# KAFKA CONSUMER
# =========================================================

consumer = KafkaConsumer(
    TASK_TOPIC,
    bootstrap_servers=BOOTSTRAP,
    group_id="cpu-workers",
    enable_auto_commit=False,
    auto_offset_reset="earliest",
    max_poll_records=1,
    max_poll_interval_ms=30 * 60 * 1000,
    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
)

print("CPU worker started, waiting for tasks...", flush=True)

# =========================================================
# MAIN LOOP
# =========================================================

for msg in consumer:
    task = None
    try:
        task = msg.value
        payload = task["payload"]
        task_type = payload.get("type")

        if task_type not in LIMITS["task_types"]:
            print(f"[worker {WORKER_ID}] Skipping unsupported: {task_type}", flush=True)
            consumer.commit()
            continue

        result = None

        # ---------------- PRIME COUNT ----------------
        if task_type == "prime_count":
            start = int(payload["start"])
            end = int(payload["end"])
            result = {"count": sum(1 for i in range(start, end) if is_prime(i))}

        # ---------------- SENTIMENT ANALYSIS ----------------
        elif task_type == "sentiment_analysis":
            texts = payload.get("texts") or payload.get("items", [])
            analyzed = [analyze_sentiment(t) for t in texts]

            positives = sum(1 for a in analyzed if a["label"] == "positive")
            negatives = sum(1 for a in analyzed if a["label"] == "negative")
            neutrals = sum(1 for a in analyzed if a["label"] == "neutral")

            scores = [a["score"] for a in analyzed if isinstance(a["score"], (int, float))]
            avg_score = sum(scores) / len(scores) if scores else 0

            result = {
                "positive": positives,
                "negative": negatives,
                "neutral": neutrals,
                "avg_score": round(avg_score, 3),
                "items": analyzed,
                "ai_powered": USE_AI_MODELS,
            }

        # ---------------- TRANSLATION ----------------
        elif task_type == "translation":
            texts = payload.get("texts") or payload.get("items", [])
            target_lang = payload.get("target", "fr")

            if isinstance(texts, str):
                texts = [texts]

            translated = [translate_text(t, target_lang) for t in texts]
            result = {
                "target_lang": target_lang,
                "translations": translated,
            }

        # ---------------- SUMMARIZATION ----------------
        elif task_type == "summarization":
            texts = payload.get("texts") or payload.get("items", [])
            max_len = payload.get("max_length", 130)

            if isinstance(texts, str):
                texts = [texts]

            summaries = [summarize_text(t, max_length=max_len) for t in texts]
            result = {"summaries": summaries}

        # ---------------- IMAGE CLASSIFICATION ----------------
        elif task_type == "image_classification":
            images = payload.get("images") or payload.get("items", [])

            if isinstance(images, str):
                images = [images]

            classifications = []
            for img_url in images:
                try:
                    classifications.append(classify_image(img_url))
                except Exception as e:
                    classifications.append({"image_url": img_url, "error": str(e)})

            result = {"classifications": classifications}

        # ---------------- TEXT GENERATION ----------------
        elif task_type == "text_generation":
            prompts = payload.get("prompts") or payload.get("items", [])
            max_len = payload.get("max_length", 100)

            if isinstance(prompts, str):
                prompts = [prompts]

            generated = [generate_text(p, max_length=max_len) for p in prompts]
            result = {"generated": generated}

        # ---------------- QUESTION ANSWERING ----------------
        elif task_type == "question_answering":
            questions = payload.get("questions") or payload.get("items", [])
            context = payload.get("context", "")

            answers = []
            for q in questions:
                if isinstance(q, dict):
                    answers.append(answer_question(q["question"], q.get("context", context)))
                else:
                    answers.append(answer_question(q, context))

            result = {"answers": answers}

        else:
            raise ValueError(f"Unsupported task type: {task_type}")

        # Send result
        producer.send(RESULT_TOPIC, {
            "job_id": task["job_id"],
            "chunk_id": task["chunk_id"],
            "worker_id": WORKER_ID,
            "result": result,
        })
        producer.flush()
        consumer.commit()

        print(
            f"[worker {WORKER_ID}] job={task['job_id']} "
            f"chunk={task['chunk_id']} done ({task_type})",
            flush=True
        )

    except Exception as e:
        print(f"Task error: {e}", flush=True)
        import traceback
        traceback.print_exc()

        producer.send(DLQ_TOPIC, {
            "worker_id": WORKER_ID,
            "error": str(e),
            "raw": task,
        })
        producer.flush()
        consumer.commit()
