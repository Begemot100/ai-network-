#!/usr/bin/env python3
"""
AI Network — Client Example
Shows how to use the API with OpenAI SDK
"""

# Option 1: Using OpenAI SDK (recommended)
def example_openai_sdk():
    """Use OpenAI SDK with AI Network"""
    from openai import OpenAI

    client = OpenAI(
        base_url="http://localhost:8000/v1",
        api_key="not-needed",  # AI Network doesn't require auth for demo
    )

    # Chat completion
    print("=== Chat ===")
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "user", "content": "Hello! What is 2+2?"}
        ]
    )
    print(f"Response: {response.choices[0].message.content}\n")

    # Image generation
    print("=== Image ===")
    response = client.images.generate(
        prompt="a beautiful sunset over mountains",
        n=1,
        size="512x512"
    )
    print(f"Image URL: {response.data[0].url}\n")


# Option 2: Using requests directly
def example_requests():
    """Use requests library directly"""
    import requests

    BASE_URL = "http://localhost:8000"

    # Chat
    print("=== Chat (requests) ===")
    resp = requests.post(f"{BASE_URL}/v1/chat/completions", json={
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": "Hello!"}]
    })
    print(f"Response: {resp.json()['choices'][0]['message']['content']}\n")

    # Image
    print("=== Image (requests) ===")
    resp = requests.post(f"{BASE_URL}/v1/images/generations", json={
        "prompt": "a cat in space",
        "size": "512x512"
    })
    print(f"Image URL: {resp.json()['data'][0]['url']}\n")


# Option 3: Using curl (from terminal)
def print_curl_examples():
    """Print curl examples"""
    print("""
=== CURL Examples ===

# Chat
curl -X POST http://localhost:8000/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{"model": "gpt-3.5-turbo", "messages": [{"role": "user", "content": "Hello!"}]}'

# Image
curl -X POST http://localhost:8000/v1/images/generations \\
  -H "Content-Type: application/json" \\
  -d '{"prompt": "a cat in space", "size": "512x512"}'

# Transcription
curl -X POST http://localhost:8000/v1/audio/transcriptions \\
  -F "file=@audio.mp3" \\
  -F "language=en"
""")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--curl":
        print_curl_examples()
    else:
        try:
            print("Testing AI Network API...\n")
            example_openai_sdk()
        except ImportError:
            print("OpenAI SDK not installed. Using requests...")
            example_requests()
        except Exception as e:
            print(f"Error: {e}")
            print("\nMake sure the API server is running:")
            print("  python api/server.py")
