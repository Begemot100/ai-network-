# AI Network SDK Examples

## Python Client

### Installation

```bash
pip install requests
```

### Basic Usage

```python
import requests

BASE_URL = "http://localhost:8050"


class AINetworkClient:
    def __init__(self, api_key: str = None):
        self.base_url = BASE_URL
        self.api_key = api_key
        self.headers = {}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

    # ============================================
    # OpenAI Compatible API
    # ============================================

    def chat(self, messages: list, model: str = "gpt-3.5-turbo", **kwargs):
        """Chat completion (OpenAI compatible)."""
        response = requests.post(
            f"{self.base_url}/v1/chat/completions",
            json={
                "model": model,
                "messages": messages,
                **kwargs
            },
            headers=self.headers
        )
        return response.json()

    def generate_image(self, prompt: str, size: str = "512x512", n: int = 1):
        """Generate image (DALL-E compatible)."""
        response = requests.post(
            f"{self.base_url}/v1/images/generations",
            json={
                "prompt": prompt,
                "size": size,
                "n": n,
            },
            headers=self.headers
        )
        return response.json()

    def transcribe(self, audio_path: str, language: str = "en"):
        """Transcribe audio (Whisper compatible)."""
        with open(audio_path, "rb") as f:
            response = requests.post(
                f"{self.base_url}/v1/audio/transcriptions",
                files={"file": f},
                data={"language": language},
                headers=self.headers
            )
        return response.json()

    def embeddings(self, text: str | list):
        """Generate embeddings."""
        response = requests.post(
            f"{self.base_url}/v1/embeddings",
            json={"input": text},
            headers=self.headers
        )
        return response.json()

    # ============================================
    # Task API
    # ============================================

    def create_task(self, prompt: str, task_type: str = "text", priority: int = 0):
        """Create a new task."""
        response = requests.post(
            f"{self.base_url}/tasks/create",
            json={
                "prompt": prompt,
                "task_type": task_type,
                "priority": priority,
            },
            headers=self.headers
        )
        return response.json()

    def get_task(self, task_id: int):
        """Get task by ID."""
        response = requests.get(
            f"{self.base_url}/tasks/{task_id}",
            headers=self.headers
        )
        return response.json()

    def list_tasks(self, status: str = None, limit: int = 20):
        """List tasks."""
        params = {"limit": limit}
        if status:
            params["status"] = status
        response = requests.get(
            f"{self.base_url}/tasks/",
            params=params,
            headers=self.headers
        )
        return response.json()

    # ============================================
    # Worker API
    # ============================================

    def register_worker(self, name: str, power: int = 10, capabilities: str = "text"):
        """Register a new worker."""
        response = requests.post(
            f"{self.base_url}/auth/worker/register",
            params={
                "name": name,
                "power": power,
                "capabilities": capabilities,
            }
        )
        return response.json()

    def get_worker(self, worker_id: int):
        """Get worker info."""
        response = requests.get(
            f"{self.base_url}/workers/{worker_id}",
            headers=self.headers
        )
        return response.json()


# ============================================
# Usage Examples
# ============================================

if __name__ == "__main__":
    client = AINetworkClient()

    # Chat example
    print("=== Chat ===")
    result = client.chat([
        {"role": "user", "content": "What is 2+2?"}
    ])
    print(result)

    # Image generation example
    print("\n=== Image Generation ===")
    result = client.generate_image(
        prompt="a beautiful sunset over mountains",
        size="512x512"
    )
    print(result)

    # Embeddings example
    print("\n=== Embeddings ===")
    result = client.embeddings("Hello, world!")
    print(f"Embedding dimension: {len(result['data'][0]['embedding'])}")

    # Task example
    print("\n=== Task ===")
    result = client.create_task(
        prompt="reverse:hello",
        task_type="reverse"
    )
    print(result)
```

---

## JavaScript/Node.js Client

```javascript
const axios = require('axios');

const BASE_URL = 'http://localhost:8050';

class AINetworkClient {
    constructor(apiKey = null) {
        this.baseUrl = BASE_URL;
        this.headers = {};
        if (apiKey) {
            this.headers['Authorization'] = `Bearer ${apiKey}`;
        }
    }

    // Chat completion
    async chat(messages, model = 'gpt-3.5-turbo', options = {}) {
        const response = await axios.post(`${this.baseUrl}/v1/chat/completions`, {
            model,
            messages,
            ...options
        }, { headers: this.headers });
        return response.data;
    }

    // Image generation
    async generateImage(prompt, size = '512x512', n = 1) {
        const response = await axios.post(`${this.baseUrl}/v1/images/generations`, {
            prompt,
            size,
            n
        }, { headers: this.headers });
        return response.data;
    }

    // Transcription
    async transcribe(audioBuffer, language = 'en') {
        const FormData = require('form-data');
        const form = new FormData();
        form.append('file', audioBuffer, 'audio.wav');
        form.append('language', language);

        const response = await axios.post(
            `${this.baseUrl}/v1/audio/transcriptions`,
            form,
            { headers: { ...this.headers, ...form.getHeaders() } }
        );
        return response.data;
    }

    // Embeddings
    async embeddings(input) {
        const response = await axios.post(`${this.baseUrl}/v1/embeddings`, {
            input
        }, { headers: this.headers });
        return response.data;
    }
}

// Usage
async function main() {
    const client = new AINetworkClient();

    // Chat
    const chatResult = await client.chat([
        { role: 'user', content: 'Hello!' }
    ]);
    console.log('Chat:', chatResult.choices[0].message.content);

    // Image
    const imageResult = await client.generateImage('a cat in space');
    console.log('Image task:', imageResult);

    // Embeddings
    const embResult = await client.embeddings('Hello, world!');
    console.log('Embedding dims:', embResult.data[0].embedding.length);
}

main().catch(console.error);
```

---

## cURL Examples

### Chat

```bash
curl -X POST http://localhost:8050/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-3.5-turbo",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### Image Generation

```bash
curl -X POST http://localhost:8050/v1/images/generations \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "a beautiful landscape",
    "size": "512x512",
    "n": 1
  }'
```

### Transcription

```bash
curl -X POST http://localhost:8050/v1/audio/transcriptions \
  -F "file=@audio.mp3" \
  -F "language=en"
```

### Embeddings

```bash
curl -X POST http://localhost:8050/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"input": "Hello, world!"}'
```

---

## Integration with OpenAI SDK

The API is compatible with OpenAI SDK. Just change the base URL:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8050/v1",
    api_key="dummy"  # Not required for local
)

# Chat
response = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)

# Image
response = client.images.generate(
    prompt="a cat in space",
    size="512x512",
    n=1
)
print(response.data[0].url)
```

```javascript
import OpenAI from 'openai';

const openai = new OpenAI({
    baseURL: 'http://localhost:8050/v1',
    apiKey: 'dummy'
});

// Chat
const response = await openai.chat.completions.create({
    model: 'gpt-3.5-turbo',
    messages: [{ role: 'user', content: 'Hello!' }]
});
console.log(response.choices[0].message.content);
```
