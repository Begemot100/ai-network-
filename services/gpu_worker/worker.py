"""
GPU Worker for Distributed AI Network.
Handles heavy AI workloads with GPU acceleration.

Supported task types:
- sentiment_analysis: Batch sentiment analysis with GPU
- embeddings: Text embeddings generation (sentence-transformers)
- text_generation: LLM text generation
- translation: Neural machine translation
- summarization: Text summarization
- image_classification: Vision model inference
- zero_shot_classification: Zero-shot text classification
- image_generation: Stable Diffusion image generation
- transcription: Whisper audio transcription
"""

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import NoBrokersAvailable, KafkaError
import json
import os
import time
import uuid
import platform
import threading
import traceback

# =========================================================
# CONFIG
# =========================================================

WORKER_ID = os.getenv("WORKER_ID", str(uuid.uuid4()))
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")

TASK_TOPIC = os.getenv("INPUT_TOPIC", "ai.tasks.gpu")
RESULT_TOPIC = os.getenv("OUTPUT_TOPIC", "ai.results.v2")
DLQ_TOPIC = "ai.dlq.gpu"
HEARTBEAT_TOPIC = "ai.workers.heartbeat"

GROUP_ID = os.getenv("KAFKA_GROUP_ID", "gpu-workers-v3")
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "5"))

# Model configuration
DEFAULT_SENTIMENT_MODEL = os.getenv(
    "SENTIMENT_MODEL",
    "distilbert-base-uncased-finetuned-sst-2-english"
)
DEFAULT_EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2"
)
DEFAULT_LLM_MODEL = os.getenv(
    "LLM_MODEL",
    "microsoft/phi-2"
)
DEFAULT_SD_MODEL = os.getenv(
    "SD_MODEL",
    "stabilityai/stable-diffusion-2-1"
)
DEFAULT_WHISPER_MODEL = os.getenv(
    "WHISPER_MODEL",
    "openai/whisper-base"
)

# Batch sizes for GPU efficiency
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "32"))
MAX_SEQ_LENGTH = int(os.getenv("MAX_SEQ_LENGTH", "512"))

# =========================================================
# GPU DETECTION
# =========================================================

def detect_gpu():
    """Detect GPU availability and return device info."""
    try:
        import torch
        if torch.cuda.is_available():
            device = "cuda"
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory // (1024**3)
            return {
                "device": device,
                "gpu_name": gpu_name,
                "gpu_memory_gb": gpu_memory,
                "cuda_version": torch.version.cuda,
            }
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            return {
                "device": "mps",
                "gpu_name": "Apple Silicon",
                "gpu_memory_gb": 0,
                "cuda_version": None,
            }
    except ImportError:
        pass

    return {
        "device": "cpu",
        "gpu_name": None,
        "gpu_memory_gb": 0,
        "cuda_version": None,
    }


GPU_INFO = detect_gpu()
DEVICE = GPU_INFO["device"]

print(f"[gpu-worker {WORKER_ID}] Starting...", flush=True)
print(f"[gpu-worker {WORKER_ID}] Device: {DEVICE}", flush=True)
if GPU_INFO["gpu_name"]:
    print(f"[gpu-worker {WORKER_ID}] GPU: {GPU_INFO['gpu_name']} ({GPU_INFO['gpu_memory_gb']}GB)", flush=True)

# =========================================================
# LAZY MODEL LOADING
# =========================================================

_models = {}
_tokenizers = {}


def get_device():
    """Get the torch device."""
    import torch
    if DEVICE == "cuda":
        return torch.device("cuda")
    elif DEVICE == "mps":
        return torch.device("mps")
    return torch.device("cpu")


def get_sentiment_model():
    """Load sentiment analysis model."""
    if "sentiment" not in _models:
        print(f"[gpu-worker {WORKER_ID}] Loading sentiment model...", flush=True)
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        import torch

        _tokenizers["sentiment"] = AutoTokenizer.from_pretrained(DEFAULT_SENTIMENT_MODEL)
        _models["sentiment"] = AutoModelForSequenceClassification.from_pretrained(
            DEFAULT_SENTIMENT_MODEL
        ).to(get_device())
        _models["sentiment"].eval()

        print(f"[gpu-worker {WORKER_ID}] Sentiment model loaded!", flush=True)

    return _models["sentiment"], _tokenizers["sentiment"]


def get_embedding_model():
    """Load embedding model (sentence-transformers)."""
    if "embedding" not in _models:
        print(f"[gpu-worker {WORKER_ID}] Loading embedding model...", flush=True)
        from sentence_transformers import SentenceTransformer

        _models["embedding"] = SentenceTransformer(
            DEFAULT_EMBEDDING_MODEL,
            device=DEVICE
        )

        print(f"[gpu-worker {WORKER_ID}] Embedding model loaded!", flush=True)

    return _models["embedding"]


def get_llm_model():
    """Load LLM model for text generation."""
    if "llm" not in _models:
        print(f"[gpu-worker {WORKER_ID}] Loading LLM model...", flush=True)
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch

        _tokenizers["llm"] = AutoTokenizer.from_pretrained(
            DEFAULT_LLM_MODEL,
            trust_remote_code=True
        )
        _models["llm"] = AutoModelForCausalLM.from_pretrained(
            DEFAULT_LLM_MODEL,
            torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32,
            trust_remote_code=True,
            device_map="auto" if DEVICE == "cuda" else None,
        )

        if _tokenizers["llm"].pad_token is None:
            _tokenizers["llm"].pad_token = _tokenizers["llm"].eos_token

        print(f"[gpu-worker {WORKER_ID}] LLM model loaded!", flush=True)

    return _models["llm"], _tokenizers["llm"]


def get_translation_model(src_lang: str, tgt_lang: str):
    """Load translation model."""
    key = f"translation_{src_lang}_{tgt_lang}"

    if key not in _models:
        print(f"[gpu-worker {WORKER_ID}] Loading translation model {src_lang}->{tgt_lang}...", flush=True)
        from transformers import MarianMTModel, MarianTokenizer

        model_name = f"Helsinki-NLP/opus-mt-{src_lang}-{tgt_lang}"

        _tokenizers[key] = MarianTokenizer.from_pretrained(model_name)
        _models[key] = MarianMTModel.from_pretrained(model_name).to(get_device())
        _models[key].eval()

        print(f"[gpu-worker {WORKER_ID}] Translation model loaded!", flush=True)

    return _models[key], _tokenizers[key]


def get_summarization_model():
    """Load summarization model."""
    if "summarization" not in _models:
        print(f"[gpu-worker {WORKER_ID}] Loading summarization model...", flush=True)
        from transformers import BartForConditionalGeneration, BartTokenizer

        _tokenizers["summarization"] = BartTokenizer.from_pretrained("facebook/bart-large-cnn")
        _models["summarization"] = BartForConditionalGeneration.from_pretrained(
            "facebook/bart-large-cnn"
        ).to(get_device())
        _models["summarization"].eval()

        print(f"[gpu-worker {WORKER_ID}] Summarization model loaded!", flush=True)

    return _models["summarization"], _tokenizers["summarization"]


def get_image_classifier():
    """Load image classification model."""
    if "image_classifier" not in _models:
        print(f"[gpu-worker {WORKER_ID}] Loading image classifier...", flush=True)
        from transformers import ViTForImageClassification, ViTImageProcessor

        _tokenizers["image_classifier"] = ViTImageProcessor.from_pretrained(
            "google/vit-base-patch16-224"
        )
        _models["image_classifier"] = ViTForImageClassification.from_pretrained(
            "google/vit-base-patch16-224"
        ).to(get_device())
        _models["image_classifier"].eval()

        print(f"[gpu-worker {WORKER_ID}] Image classifier loaded!", flush=True)

    return _models["image_classifier"], _tokenizers["image_classifier"]


def get_zero_shot_classifier():
    """Load zero-shot classification model."""
    if "zero_shot" not in _models:
        print(f"[gpu-worker {WORKER_ID}] Loading zero-shot classifier...", flush=True)
        from transformers import pipeline

        _models["zero_shot"] = pipeline(
            "zero-shot-classification",
            model="facebook/bart-large-mnli",
            device=0 if DEVICE == "cuda" else -1
        )

        print(f"[gpu-worker {WORKER_ID}] Zero-shot classifier loaded!", flush=True)

    return _models["zero_shot"]


def get_stable_diffusion():
    """Load Stable Diffusion pipeline."""
    if "sd" not in _models:
        print(f"[gpu-worker {WORKER_ID}] Loading Stable Diffusion...", flush=True)
        import torch
        from diffusers import StableDiffusionPipeline, DPMSolverMultistepScheduler

        pipe = StableDiffusionPipeline.from_pretrained(
            DEFAULT_SD_MODEL,
            torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32,
        )

        # Use faster scheduler
        pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)

        if DEVICE == "cuda":
            pipe = pipe.to("cuda")
            # Enable memory optimizations
            pipe.enable_attention_slicing()
            try:
                pipe.enable_xformers_memory_efficient_attention()
            except:
                pass  # xformers not available

        _models["sd"] = pipe
        print(f"[gpu-worker {WORKER_ID}] Stable Diffusion loaded!", flush=True)

    return _models["sd"]


def get_whisper():
    """Load Whisper model for transcription."""
    if "whisper" not in _models:
        print(f"[gpu-worker {WORKER_ID}] Loading Whisper...", flush=True)
        import torch
        from transformers import WhisperProcessor, WhisperForConditionalGeneration

        _tokenizers["whisper"] = WhisperProcessor.from_pretrained(DEFAULT_WHISPER_MODEL)
        _models["whisper"] = WhisperForConditionalGeneration.from_pretrained(
            DEFAULT_WHISPER_MODEL,
            torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32,
        ).to(get_device())

        print(f"[gpu-worker {WORKER_ID}] Whisper loaded!", flush=True)

    return _models["whisper"], _tokenizers["whisper"]


# =========================================================
# TASK HANDLERS
# =========================================================

def handle_sentiment_analysis(payload: dict) -> dict:
    """
    Batch sentiment analysis with GPU acceleration.

    Input: {"texts": ["text1", "text2", ...]}
    Output: {"positive": N, "negative": N, "neutral": N, "items": [...]}
    """
    import torch

    texts = payload.get("texts") or payload.get("items", [])
    if isinstance(texts, str):
        texts = [texts]

    model, tokenizer = get_sentiment_model()
    device = get_device()

    results = []
    label_map = {0: "negative", 1: "positive"}

    # Process in batches
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]

        inputs = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=MAX_SEQ_LENGTH,
            return_tensors="pt"
        ).to(device)

        with torch.no_grad():
            outputs = model(**inputs)
            probs = torch.softmax(outputs.logits, dim=-1)
            predictions = torch.argmax(probs, dim=-1)

        for j, text in enumerate(batch):
            pred_idx = predictions[j].item()
            score = probs[j][pred_idx].item()

            results.append({
                "text": text[:100] + "..." if len(text) > 100 else text,
                "label": label_map.get(pred_idx, "neutral"),
                "score": round(score, 4),
            })

    # Aggregate
    positives = sum(1 for r in results if r["label"] == "positive")
    negatives = sum(1 for r in results if r["label"] == "negative")
    neutrals = len(results) - positives - negatives

    scores = [r["score"] for r in results]
    avg_score = sum(scores) / len(scores) if scores else 0

    return {
        "positive": positives,
        "negative": negatives,
        "neutral": neutrals,
        "avg_score": round(avg_score, 4),
        "items": results,
        "model": DEFAULT_SENTIMENT_MODEL,
        "device": DEVICE,
    }


def handle_embeddings(payload: dict) -> dict:
    """
    Generate text embeddings using sentence-transformers.

    Input: {"texts": ["text1", "text2", ...]}
    Output: {"embeddings": [[...], [...], ...], "dimension": N}
    """
    texts = payload.get("texts") or payload.get("items", [])
    if isinstance(texts, str):
        texts = [texts]

    model = get_embedding_model()

    # Generate embeddings
    embeddings = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=False,
        convert_to_numpy=True
    )

    return {
        "embeddings": embeddings.tolist(),
        "dimension": embeddings.shape[1],
        "count": len(texts),
        "model": DEFAULT_EMBEDDING_MODEL,
        "device": DEVICE,
    }


def handle_text_generation(payload: dict) -> dict:
    """
    Generate text using LLM.

    Input: {"prompts": ["prompt1", ...], "max_length": 100, "temperature": 0.7}
    Output: {"generated": [{"prompt": "...", "text": "..."}]}
    """
    import torch

    prompts = payload.get("prompts") or payload.get("items", [])
    if isinstance(prompts, str):
        prompts = [prompts]

    max_length = payload.get("max_length", 100)
    temperature = payload.get("temperature", 0.7)
    top_p = payload.get("top_p", 0.9)

    model, tokenizer = get_llm_model()

    results = []
    for prompt in prompts:
        inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512)

        if DEVICE == "cuda":
            inputs = {k: v.cuda() for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=max_length,
                temperature=temperature,
                top_p=top_p,
                do_sample=True,
                pad_token_id=tokenizer.pad_token_id,
            )

        generated_text = tokenizer.decode(outputs[0], skip_special_tokens=True)

        results.append({
            "prompt": prompt,
            "generated_text": generated_text,
        })

    return {
        "generated": results,
        "model": DEFAULT_LLM_MODEL,
        "device": DEVICE,
    }


def handle_translation(payload: dict) -> dict:
    """
    Translate text using MarianMT.

    Input: {"texts": [...], "source": "en", "target": "fr"}
    Output: {"translations": [...]}
    """
    import torch

    texts = payload.get("texts") or payload.get("items", [])
    if isinstance(texts, str):
        texts = [texts]

    src_lang = payload.get("source", "en")
    tgt_lang = payload.get("target", "fr")

    model, tokenizer = get_translation_model(src_lang, tgt_lang)
    device = get_device()

    results = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]

        inputs = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=MAX_SEQ_LENGTH,
            return_tensors="pt"
        ).to(device)

        with torch.no_grad():
            outputs = model.generate(**inputs)

        translations = tokenizer.batch_decode(outputs, skip_special_tokens=True)

        for j, text in enumerate(batch):
            results.append({
                "source_text": text,
                "translated_text": translations[j],
                "source_lang": src_lang,
                "target_lang": tgt_lang,
            })

    return {
        "translations": results,
        "source_lang": src_lang,
        "target_lang": tgt_lang,
        "device": DEVICE,
    }


def handle_summarization(payload: dict) -> dict:
    """
    Summarize text using BART.

    Input: {"texts": [...], "max_length": 130, "min_length": 30}
    Output: {"summaries": [...]}
    """
    import torch

    texts = payload.get("texts") or payload.get("items", [])
    if isinstance(texts, str):
        texts = [texts]

    max_length = payload.get("max_length", 130)
    min_length = payload.get("min_length", 30)

    model, tokenizer = get_summarization_model()
    device = get_device()

    results = []

    for text in texts:
        if len(text) < 100:
            results.append({
                "original_length": len(text),
                "summary": text,
                "note": "Text too short",
            })
            continue

        inputs = tokenizer(
            text,
            truncation=True,
            max_length=1024,
            return_tensors="pt"
        ).to(device)

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_length=max_length,
                min_length=min_length,
                do_sample=False,
            )

        summary = tokenizer.decode(outputs[0], skip_special_tokens=True)

        results.append({
            "original_length": len(text),
            "summary": summary,
            "summary_length": len(summary),
        })

    return {
        "summaries": results,
        "device": DEVICE,
    }


def handle_image_classification(payload: dict) -> dict:
    """
    Classify images using ViT.

    Input: {"images": ["url1", "url2", ...]}
    Output: {"classifications": [...]}
    """
    import torch
    import requests
    from PIL import Image
    from io import BytesIO

    images = payload.get("images") or payload.get("items", [])
    if isinstance(images, str):
        images = [images]

    model, processor = get_image_classifier()
    device = get_device()

    results = []

    for img_url in images:
        try:
            response = requests.get(img_url, timeout=30)
            response.raise_for_status()
            image = Image.open(BytesIO(response.content)).convert("RGB")

            inputs = processor(images=image, return_tensors="pt").to(device)

            with torch.no_grad():
                outputs = model(**inputs)
                probs = torch.softmax(outputs.logits, dim=-1)[0]

            # Top 5 predictions
            top_probs, top_indices = probs.topk(5)

            predictions = []
            for prob, idx in zip(top_probs, top_indices):
                label = model.config.id2label[idx.item()]
                predictions.append({
                    "label": label,
                    "score": round(prob.item(), 4),
                })

            results.append({
                "image_url": img_url,
                "predictions": predictions,
            })

        except Exception as e:
            results.append({
                "image_url": img_url,
                "error": str(e),
            })

    return {
        "classifications": results,
        "device": DEVICE,
    }


def handle_zero_shot_classification(payload: dict) -> dict:
    """
    Zero-shot text classification.

    Input: {"texts": [...], "labels": ["label1", "label2", ...]}
    Output: {"classifications": [...]}
    """
    texts = payload.get("texts") or payload.get("items", [])
    if isinstance(texts, str):
        texts = [texts]

    labels = payload.get("labels", ["positive", "negative", "neutral"])

    classifier = get_zero_shot_classifier()

    results = []
    for text in texts:
        result = classifier(text, labels)
        results.append({
            "text": text[:100] + "..." if len(text) > 100 else text,
            "labels": result["labels"],
            "scores": [round(s, 4) for s in result["scores"]],
            "best_label": result["labels"][0],
            "best_score": round(result["scores"][0], 4),
        })

    return {
        "classifications": results,
        "labels": labels,
        "device": DEVICE,
    }


def handle_image_generation(payload: dict) -> dict:
    """
    Generate images using Stable Diffusion.

    Input: {
        "prompt": "a cat in space",
        "negative_prompt": "blurry, bad quality",
        "width": 512,
        "height": 512,
        "num_images": 1,
        "steps": 25,
        "guidance_scale": 7.5,
        "seed": null
    }
    Output: {"images": [{"base64": "...", "seed": 123}]}
    """
    import torch
    import base64
    from io import BytesIO

    prompt = payload.get("prompt", "")
    negative_prompt = payload.get("negative_prompt", "")
    width = payload.get("width", 512)
    height = payload.get("height", 512)
    num_images = min(payload.get("num_images", 1), 4)  # Max 4 images
    steps = min(payload.get("steps", 25), 50)  # Max 50 steps
    guidance_scale = payload.get("guidance_scale", 7.5)
    seed = payload.get("seed")

    pipe = get_stable_diffusion()

    # Set seed for reproducibility
    generator = None
    if seed is not None:
        generator = torch.Generator(device=DEVICE).manual_seed(seed)
    else:
        seed = torch.randint(0, 2**32, (1,)).item()
        generator = torch.Generator(device=DEVICE).manual_seed(seed)

    results = []

    for i in range(num_images):
        current_seed = seed + i
        gen = torch.Generator(device=DEVICE).manual_seed(current_seed)

        with torch.inference_mode():
            image = pipe(
                prompt=prompt,
                negative_prompt=negative_prompt if negative_prompt else None,
                width=width,
                height=height,
                num_inference_steps=steps,
                guidance_scale=guidance_scale,
                generator=gen,
            ).images[0]

        # Convert to base64
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        img_base64 = base64.b64encode(buffer.getvalue()).decode()

        results.append({
            "base64": img_base64,
            "seed": current_seed,
            "width": width,
            "height": height,
        })

    return {
        "images": results,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "steps": steps,
        "guidance_scale": guidance_scale,
        "model": DEFAULT_SD_MODEL,
        "device": DEVICE,
    }


def handle_transcription(payload: dict) -> dict:
    """
    Transcribe audio using Whisper.

    Input: {
        "audio_url": "https://...",
        "audio_base64": "...",
        "language": "en",
        "task": "transcribe"  # or "translate"
    }
    Output: {"text": "...", "segments": [...]}
    """
    import torch
    import requests
    import base64
    import numpy as np
    from io import BytesIO

    model, processor = get_whisper()
    device = get_device()

    # Get audio data
    audio_data = None
    if "audio_base64" in payload:
        audio_data = base64.b64decode(payload["audio_base64"])
    elif "audio_url" in payload:
        response = requests.get(payload["audio_url"], timeout=60)
        response.raise_for_status()
        audio_data = response.content
    else:
        raise ValueError("Either audio_url or audio_base64 required")

    # Load audio using librosa
    import librosa
    audio_array, sr = librosa.load(BytesIO(audio_data), sr=16000)

    # Process audio
    input_features = processor(
        audio_array,
        sampling_rate=16000,
        return_tensors="pt"
    ).input_features.to(device)

    # Generate transcription
    language = payload.get("language", "en")
    task = payload.get("task", "transcribe")

    forced_decoder_ids = processor.get_decoder_prompt_ids(
        language=language,
        task=task
    )

    with torch.inference_mode():
        predicted_ids = model.generate(
            input_features,
            forced_decoder_ids=forced_decoder_ids,
            max_length=448,
        )

    transcription = processor.batch_decode(
        predicted_ids,
        skip_special_tokens=True
    )[0]

    return {
        "text": transcription.strip(),
        "language": language,
        "task": task,
        "duration_seconds": len(audio_array) / 16000,
        "model": DEFAULT_WHISPER_MODEL,
        "device": DEVICE,
    }


# =========================================================
# TASK ROUTER
# =========================================================

TASK_HANDLERS = {
    "sentiment_analysis": handle_sentiment_analysis,
    "embeddings": handle_embeddings,
    "text_generation": handle_text_generation,
    "translation": handle_translation,
    "summarization": handle_summarization,
    "image_classification": handle_image_classification,
    "zero_shot_classification": handle_zero_shot_classification,
    "image_generation": handle_image_generation,
    "transcription": handle_transcription,
}

SUPPORTED_TYPES = list(TASK_HANDLERS.keys())


# =========================================================
# KAFKA SETUP
# =========================================================

def safe_json(m: bytes):
    """Safely deserialize JSON."""
    try:
        return json.loads(m.decode("utf-8"))
    except Exception as e:
        print(f"[gpu-worker {WORKER_ID}] Bad message skipped: {e}", flush=True)
        return None


# Connect to Kafka with retry
producer = None
while producer is None:
    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            retries=5,
            retry_backoff_ms=2000,
        )
        print(f"[gpu-worker {WORKER_ID}] Kafka producer connected", flush=True)
    except NoBrokersAvailable:
        print(f"[gpu-worker {WORKER_ID}] Kafka not ready, retrying in 2s...", flush=True)
        time.sleep(2)


# =========================================================
# HEARTBEAT
# =========================================================

def get_gpu_stats():
    """Get GPU memory usage statistics."""
    try:
        import torch
        if torch.cuda.is_available():
            return {
                "gpu_memory_used_mb": torch.cuda.memory_allocated() // (1024**2),
                "gpu_memory_cached_mb": torch.cuda.memory_reserved() // (1024**2),
            }
    except:
        pass
    return {}


def heartbeat_loop():
    """Send periodic heartbeat with worker stats."""
    import psutil

    while True:
        try:
            stats = {
                "worker_id": WORKER_ID,
                "worker_type": "gpu",
                "device": DEVICE,
                "gpu_info": GPU_INFO,
                "cpu_percent": psutil.cpu_percent(),
                "ram_mb": psutil.virtual_memory().used // (1024**2),
                "loaded_models": list(_models.keys()),
                "supported_tasks": SUPPORTED_TYPES,
                "ts": int(time.time()),
                "system": {
                    "os": platform.system(),
                    "arch": platform.machine(),
                    "python": platform.python_version(),
                },
            }
            stats.update(get_gpu_stats())

            producer.send(HEARTBEAT_TOPIC, stats)
            producer.flush()

        except Exception as e:
            print(f"[gpu-worker {WORKER_ID}] Heartbeat error: {e}", flush=True)

        time.sleep(HEARTBEAT_INTERVAL)


threading.Thread(target=heartbeat_loop, daemon=True).start()
print(f"[gpu-worker {WORKER_ID}] Heartbeat started", flush=True)


# =========================================================
# KAFKA CONSUMER
# =========================================================

consumer = KafkaConsumer(
    TASK_TOPIC,
    bootstrap_servers=KAFKA_BOOTSTRAP,
    group_id=GROUP_ID,
    auto_offset_reset="latest",
    enable_auto_commit=False,
    value_deserializer=safe_json,
    max_poll_records=1,
    max_poll_interval_ms=30 * 60 * 1000,  # 30 minutes for heavy tasks
)

print(f"[gpu-worker {WORKER_ID}] Consumer started, waiting for tasks...", flush=True)
print(f"[gpu-worker {WORKER_ID}] Supported task types: {SUPPORTED_TYPES}", flush=True)


# =========================================================
# MAIN LOOP
# =========================================================

for msg in consumer:
    task = None
    start_time = time.time()

    try:
        task = msg.value
        if task is None:
            consumer.commit()
            continue

        job_id = task.get("job_id", "unknown")
        chunk_id = task.get("chunk_id", 0)
        payload = task.get("payload", {})
        task_type = payload.get("type", "sentiment_analysis")

        print(f"[gpu-worker {WORKER_ID}] Processing job={job_id} chunk={chunk_id} type={task_type}", flush=True)

        # Get handler
        if task_type not in TASK_HANDLERS:
            raise ValueError(f"Unsupported task type: {task_type}. Supported: {SUPPORTED_TYPES}")

        handler = TASK_HANDLERS[task_type]

        # Execute task
        result = handler(payload)

        # Add processing metadata
        processing_time_ms = int((time.time() - start_time) * 1000)
        result["processing_time_ms"] = processing_time_ms
        result["worker_id"] = WORKER_ID

        # Send result
        producer.send(
            RESULT_TOPIC,
            {
                "job_id": job_id,
                "chunk_id": chunk_id,
                "worker_id": WORKER_ID,
                "worker_type": "gpu",
                "result": result,
                "processing_time_ms": processing_time_ms,
            },
        )
        producer.flush()
        consumer.commit()

        print(
            f"[gpu-worker {WORKER_ID}] Completed job={job_id} chunk={chunk_id} "
            f"type={task_type} time={processing_time_ms}ms",
            flush=True,
        )

    except Exception as e:
        print(f"[gpu-worker {WORKER_ID}] Error: {e}", flush=True)
        traceback.print_exc()

        # Send to DLQ
        try:
            producer.send(
                DLQ_TOPIC,
                {
                    "worker_id": WORKER_ID,
                    "worker_type": "gpu",
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                    "raw_task": task,
                    "ts": int(time.time()),
                },
            )
            producer.flush()
        except KafkaError as ke:
            print(f"[gpu-worker {WORKER_ID}] DLQ send failed: {ke}", flush=True)

        consumer.commit()
