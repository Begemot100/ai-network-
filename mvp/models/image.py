"""
Image Generation Model
Uses Stable Diffusion via diffusers
"""

import os
import base64
from io import BytesIO

USE_REAL_MODEL = os.getenv("USE_REAL_MODEL", "false").lower() == "true"

_pipe = None

def load_model():
    """Load Stable Diffusion model"""
    global _pipe

    if not USE_REAL_MODEL:
        print("[Image] Using placeholder images")
        return

    try:
        import torch
        from diffusers import StableDiffusionPipeline, DPMSolverMultistepScheduler

        model_id = os.getenv("SD_MODEL", "stabilityai/stable-diffusion-2-1-base")
        print(f"[Image] Loading {model_id}...")

        _pipe = StableDiffusionPipeline.from_pretrained(
            model_id,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        )

        # Use faster scheduler
        _pipe.scheduler = DPMSolverMultistepScheduler.from_config(_pipe.scheduler.config)

        if torch.cuda.is_available():
            _pipe = _pipe.to("cuda")
            _pipe.enable_attention_slicing()

        print(f"[Image] Model loaded: {model_id}")

    except Exception as e:
        print(f"[Image] Failed to load model: {e}")
        print("[Image] Falling back to placeholder images")

def generate(prompt: str, width: int = 512, height: int = 512, steps: int = 25) -> str:
    """Generate image and return as base64 or URL"""

    if not USE_REAL_MODEL or _pipe is None:
        return generate_placeholder(prompt, width, height)

    try:
        import torch

        # Generate image
        with torch.inference_mode():
            image = _pipe(
                prompt,
                width=width,
                height=height,
                num_inference_steps=steps,
                guidance_scale=7.5,
            ).images[0]

        # Convert to base64
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        img_base64 = base64.b64encode(buffer.getvalue()).decode()

        return f"data:image/png;base64,{img_base64}"

    except Exception as e:
        print(f"[Image] Generation error: {e}")
        return generate_placeholder(prompt, width, height)

def generate_placeholder(prompt: str, width: int, height: int) -> str:
    """Return placeholder image URL"""
    # Use placeholder service
    text = prompt[:30].replace(" ", "+") if prompt else "AI+Image"
    return f"https://placehold.co/{width}x{height}/1a1a2e/10b981?text={text}"
