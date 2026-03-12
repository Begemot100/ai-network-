"""
Text Generation Model
Uses transformers or returns mock response
"""

import os

# Try to load real model, fallback to mock
USE_REAL_MODEL = os.getenv("USE_REAL_MODEL", "false").lower() == "true"

_model = None
_tokenizer = None

def load_model():
    """Load text generation model"""
    global _model, _tokenizer

    if not USE_REAL_MODEL:
        print("[Text] Using mock responses")
        return

    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch

        model_name = os.getenv("TEXT_MODEL", "microsoft/DialoGPT-small")
        print(f"[Text] Loading {model_name}...")

        _tokenizer = AutoTokenizer.from_pretrained(model_name)
        _model = AutoModelForCausalLM.from_pretrained(model_name)

        if torch.cuda.is_available():
            _model = _model.cuda()

        print(f"[Text] Model loaded: {model_name}")

    except Exception as e:
        print(f"[Text] Failed to load model: {e}")
        print("[Text] Falling back to mock responses")

def generate(prompt: str, max_tokens: int = 256, temperature: float = 0.7) -> str:
    """Generate text response"""

    # Mock responses for demo
    if not USE_REAL_MODEL or _model is None:
        return generate_mock(prompt)

    try:
        import torch

        inputs = _tokenizer.encode(prompt, return_tensors="pt")
        if torch.cuda.is_available():
            inputs = inputs.cuda()

        outputs = _model.generate(
            inputs,
            max_new_tokens=max_tokens,
            temperature=temperature,
            do_sample=True,
            pad_token_id=_tokenizer.eos_token_id,
        )

        response = _tokenizer.decode(outputs[0], skip_special_tokens=True)
        # Remove the prompt from response
        response = response[len(prompt):].strip()

        return response if response else "I understand. How can I help you?"

    except Exception as e:
        return f"Error generating response: {e}"

def generate_mock(prompt: str) -> str:
    """Generate mock response based on prompt"""
    prompt_lower = prompt.lower()

    if "hello" in prompt_lower or "hi" in prompt_lower:
        return "Hello! I'm an AI assistant powered by AI Network. How can I help you today?"

    if "2+2" in prompt_lower or "2 + 2" in prompt_lower:
        return "2 + 2 equals 4."

    if "weather" in prompt_lower:
        return "I don't have access to real-time weather data, but I hope it's nice where you are!"

    if "who are you" in prompt_lower or "what are you" in prompt_lower:
        return "I'm an AI assistant running on the decentralized AI Network. I can help with questions, generate images, and transcribe audio."

    if "code" in prompt_lower or "python" in prompt_lower:
        return "Here's a simple Python example:\n\n```python\ndef hello():\n    print('Hello, World!')\n\nhello()\n```"

    if "?" in prompt:
        return "That's an interesting question! Based on my knowledge, I would say it depends on the specific context. Could you provide more details?"

    return f"I received your message. This is a demo response from AI Network. In production, this would be processed by a real LLM."
