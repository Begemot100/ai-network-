<template>
  <div>
    <h1 class="text-2xl font-bold mb-6">AI Playground</h1>

    <!-- Mode Selector -->
    <div class="flex space-x-2 mb-6">
      <button
        v-for="m in modes"
        :key="m.id"
        @click="mode = m.id"
        class="px-4 py-2 rounded-lg font-medium transition-colors"
        :class="mode === m.id
          ? 'bg-green-600 text-white'
          : 'bg-gray-700 text-gray-300 hover:bg-gray-600'"
      >
        {{ m.name }}
      </button>
    </div>

    <!-- Image Generation -->
    <div v-if="mode === 'image'" class="bg-gray-800 rounded-lg p-6 border border-gray-700">
      <h2 class="text-lg font-semibold mb-4">Image Generation (Stable Diffusion)</h2>

      <div class="space-y-4">
        <div>
          <label class="block text-sm text-gray-400 mb-1">Prompt</label>
          <textarea
            v-model="imageForm.prompt"
            class="w-full bg-gray-700 border border-gray-600 rounded-lg p-3 text-white"
            rows="3"
            placeholder="A beautiful sunset over mountains, digital art, 4k..."
          ></textarea>
        </div>

        <div>
          <label class="block text-sm text-gray-400 mb-1">Negative Prompt</label>
          <input
            v-model="imageForm.negative_prompt"
            class="w-full bg-gray-700 border border-gray-600 rounded-lg p-3 text-white"
            placeholder="blurry, bad quality, distorted..."
          />
        </div>

        <div class="grid grid-cols-3 gap-4">
          <div>
            <label class="block text-sm text-gray-400 mb-1">Size</label>
            <select v-model="imageForm.size" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-3 text-white">
              <option value="512x512">512x512</option>
              <option value="768x768">768x768</option>
              <option value="1024x1024">1024x1024</option>
              <option value="512x768">512x768 (Portrait)</option>
              <option value="768x512">768x512 (Landscape)</option>
            </select>
          </div>
          <div>
            <label class="block text-sm text-gray-400 mb-1">Steps</label>
            <input
              v-model.number="imageForm.steps"
              type="number"
              min="10"
              max="50"
              class="w-full bg-gray-700 border border-gray-600 rounded-lg p-3 text-white"
            />
          </div>
          <div>
            <label class="block text-sm text-gray-400 mb-1">Images</label>
            <input
              v-model.number="imageForm.n"
              type="number"
              min="1"
              max="4"
              class="w-full bg-gray-700 border border-gray-600 rounded-lg p-3 text-white"
            />
          </div>
        </div>

        <button
          @click="generateImage"
          :disabled="loading"
          class="w-full bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white font-medium py-3 rounded-lg transition-colors"
        >
          {{ loading ? 'Generating...' : 'Generate Image' }}
        </button>
      </div>

      <!-- Results -->
      <div v-if="imageResult" class="mt-6">
        <div class="text-sm text-gray-400 mb-2">Generated Images:</div>
        <div class="grid grid-cols-2 gap-4">
          <div v-for="(img, i) in imageResult.images" :key="i" class="bg-gray-700 rounded-lg p-2">
            <img :src="img.url" class="w-full rounded" :alt="img.prompt" />
            <div class="text-xs text-gray-400 mt-2 truncate">{{ img.prompt }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Chat -->
    <div v-if="mode === 'chat'" class="bg-gray-800 rounded-lg p-6 border border-gray-700">
      <h2 class="text-lg font-semibold mb-4">Chat (LLM)</h2>

      <div class="space-y-4">
        <!-- Messages -->
        <div class="bg-gray-900 rounded-lg p-4 h-64 overflow-y-auto">
          <div v-for="(msg, i) in chatMessages" :key="i" class="mb-3">
            <div :class="msg.role === 'user' ? 'text-blue-400' : 'text-green-400'" class="text-sm font-medium">
              {{ msg.role === 'user' ? 'You' : 'AI' }}
            </div>
            <div class="text-gray-300">{{ msg.content }}</div>
          </div>
          <div v-if="chatMessages.length === 0" class="text-gray-500 text-center">
            Start a conversation...
          </div>
        </div>

        <div class="flex space-x-2">
          <input
            v-model="chatInput"
            @keyup.enter="sendChat"
            class="flex-1 bg-gray-700 border border-gray-600 rounded-lg p-3 text-white"
            placeholder="Type your message..."
          />
          <button
            @click="sendChat"
            :disabled="loading"
            class="bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white px-6 rounded-lg transition-colors"
          >
            Send
          </button>
        </div>
      </div>
    </div>

    <!-- Transcription -->
    <div v-if="mode === 'transcribe'" class="bg-gray-800 rounded-lg p-6 border border-gray-700">
      <h2 class="text-lg font-semibold mb-4">Audio Transcription (Whisper)</h2>

      <div class="space-y-4">
        <div>
          <label class="block text-sm text-gray-400 mb-1">Audio File</label>
          <input
            type="file"
            @change="onFileSelect"
            accept="audio/*"
            class="w-full bg-gray-700 border border-gray-600 rounded-lg p-3 text-white"
          />
        </div>

        <div>
          <label class="block text-sm text-gray-400 mb-1">Language</label>
          <select v-model="transcribeForm.language" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-3 text-white">
            <option value="en">English</option>
            <option value="es">Spanish</option>
            <option value="fr">French</option>
            <option value="de">German</option>
            <option value="ru">Russian</option>
            <option value="zh">Chinese</option>
            <option value="ja">Japanese</option>
          </select>
        </div>

        <button
          @click="transcribeAudio"
          :disabled="loading || !audioFile"
          class="w-full bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white font-medium py-3 rounded-lg transition-colors"
        >
          {{ loading ? 'Transcribing...' : 'Transcribe' }}
        </button>
      </div>

      <div v-if="transcribeResult" class="mt-6 p-4 bg-gray-700 rounded-lg">
        <div class="text-sm text-gray-400 mb-2">Result:</div>
        <div class="text-white">{{ transcribeResult.text }}</div>
      </div>
    </div>

    <!-- Embeddings -->
    <div v-if="mode === 'embeddings'" class="bg-gray-800 rounded-lg p-6 border border-gray-700">
      <h2 class="text-lg font-semibold mb-4">Text Embeddings</h2>

      <div class="space-y-4">
        <div>
          <label class="block text-sm text-gray-400 mb-1">Text</label>
          <textarea
            v-model="embeddingsText"
            class="w-full bg-gray-700 border border-gray-600 rounded-lg p-3 text-white"
            rows="4"
            placeholder="Enter text to generate embeddings..."
          ></textarea>
        </div>

        <button
          @click="generateEmbeddings"
          :disabled="loading"
          class="w-full bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white font-medium py-3 rounded-lg transition-colors"
        >
          {{ loading ? 'Generating...' : 'Generate Embeddings' }}
        </button>
      </div>

      <div v-if="embeddingsResult" class="mt-6 p-4 bg-gray-700 rounded-lg">
        <div class="text-sm text-gray-400 mb-2">Embedding (384 dimensions):</div>
        <div class="text-xs text-gray-300 font-mono break-all">
          [{{ embeddingsResult.data[0].embedding.slice(0, 10).map(x => x.toFixed(4)).join(', ') }}, ...]
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios'

export default {
  data() {
    return {
      mode: 'image',
      modes: [
        { id: 'image', name: 'Image Generation' },
        { id: 'chat', name: 'Chat' },
        { id: 'transcribe', name: 'Transcription' },
        { id: 'embeddings', name: 'Embeddings' },
      ],
      loading: false,

      // Image form
      imageForm: {
        prompt: '',
        negative_prompt: 'blurry, bad quality, distorted',
        size: '512x512',
        steps: 25,
        n: 1,
      },
      imageResult: null,

      // Chat
      chatMessages: [],
      chatInput: '',

      // Transcription
      audioFile: null,
      transcribeForm: {
        language: 'en',
      },
      transcribeResult: null,

      // Embeddings
      embeddingsText: '',
      embeddingsResult: null,
    }
  },
  methods: {
    async generateImage() {
      this.loading = true
      this.imageResult = null
      try {
        const res = await axios.post('/api/v1/images/generations', {
          prompt: this.imageForm.prompt,
          n: this.imageForm.n,
          size: this.imageForm.size,
          quality: this.imageForm.steps > 30 ? 'hd' : 'standard',
        })
        this.imageResult = {
          images: res.data.data.map(d => ({
            url: d.url,
            prompt: d.revised_prompt || this.imageForm.prompt
          }))
        }
      } catch (e) {
        console.error(e)
        alert('Error: ' + (e.response?.data?.detail || e.message))
      }
      this.loading = false
    },

    async sendChat() {
      if (!this.chatInput.trim()) return

      this.chatMessages.push({
        role: 'user',
        content: this.chatInput,
      })

      const input = this.chatInput
      this.chatInput = ''
      this.loading = true

      try {
        const res = await axios.post('/api/v1/chat/completions', {
          model: 'gpt-3.5-turbo',
          messages: this.chatMessages,
        })

        this.chatMessages.push({
          role: 'assistant',
          content: res.data.choices[0].message.content,
        })
      } catch (e) {
        console.error(e)
        this.chatMessages.push({
          role: 'assistant',
          content: 'Error: ' + (e.response?.data?.detail || e.message),
        })
      }
      this.loading = false
    },

    onFileSelect(e) {
      this.audioFile = e.target.files[0]
    },

    async transcribeAudio() {
      if (!this.audioFile) return

      this.loading = true
      try {
        const formData = new FormData()
        formData.append('file', this.audioFile)
        formData.append('language', this.transcribeForm.language)

        const res = await axios.post('/api/v1/audio/transcriptions', formData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        })

        this.transcribeResult = res.data
      } catch (e) {
        console.error(e)
        alert('Error: ' + (e.response?.data?.detail || e.message))
      }
      this.loading = false
    },

    async generateEmbeddings() {
      if (!this.embeddingsText.trim()) return

      this.loading = true
      try {
        const res = await axios.post('/api/v1/embeddings', {
          input: this.embeddingsText,
          model: 'text-embedding-ada-002',
        })
        this.embeddingsResult = res.data
      } catch (e) {
        console.error(e)
        alert('Error: ' + (e.response?.data?.detail || e.message))
      }
      this.loading = false
    },
  }
}
</script>
