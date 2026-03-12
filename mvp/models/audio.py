"""
Audio Transcription Model
Uses Whisper via transformers
"""

import os
import base64
import tempfile

USE_REAL_MODEL = os.getenv("USE_REAL_MODEL", "false").lower() == "true"

_model = None
_processor = None

def load_model():
    """Load Whisper model"""
    global _model, _processor

    if not USE_REAL_MODEL:
        print("[Audio] Using mock transcription")
        return

    try:
        import torch
        from transformers import WhisperProcessor, WhisperForConditionalGeneration

        model_id = os.getenv("WHISPER_MODEL", "openai/whisper-small")
        print(f"[Audio] Loading {model_id}...")

        _processor = WhisperProcessor.from_pretrained(model_id)
        _model = WhisperForConditionalGeneration.from_pretrained(model_id)

        if torch.cuda.is_available():
            _model = _model.cuda()

        print(f"[Audio] Model loaded: {model_id}")

    except Exception as e:
        print(f"[Audio] Failed to load model: {e}")
        print("[Audio] Falling back to mock transcription")

def transcribe(audio_base64: str, language: str = "en") -> str:
    """Transcribe audio from base64"""

    if not USE_REAL_MODEL or _model is None:
        return transcribe_mock(language)

    try:
        import torch
        import librosa

        # Decode base64 to audio file
        audio_bytes = base64.b64decode(audio_base64)

        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            temp_path = f.name

        # Load audio
        audio, sr = librosa.load(temp_path, sr=16000)

        # Process
        inputs = _processor(audio, sampling_rate=16000, return_tensors="pt")

        if torch.cuda.is_available():
            inputs = {k: v.cuda() for k, v in inputs.items()}

        # Generate
        with torch.no_grad():
            generated_ids = _model.generate(
                inputs["input_features"],
                language=language,
                task="transcribe",
            )

        transcription = _processor.batch_decode(generated_ids, skip_special_tokens=True)[0]

        # Cleanup
        os.unlink(temp_path)

        return transcription

    except Exception as e:
        return f"Transcription error: {e}"

def transcribe_mock(language: str = "en") -> str:
    """Return mock transcription"""
    return f"[Mock transcription] This is a demo transcription. In production, Whisper would process your audio file and return the actual text. Language: {language}"
