<template>
  <div class="max-w-2xl">
    <h1 class="text-2xl font-bold mb-6">Create New Batch Job</h1>

    <div class="bg-gray-800 rounded-lg border border-gray-700 p-6">
      <!-- Task Type -->
      <div class="mb-4">
        <label class="block text-sm text-gray-400 mb-2">Task Type</label>
        <select v-model="taskType" class="w-full bg-gray-700 rounded px-4 py-2">
          <option value="sentiment_analysis">Sentiment Analysis</option>
          <option value="translation">Translation</option>
          <option value="summarization">Summarization</option>
          <option value="image_classification">Image Classification</option>
          <option value="text_generation">Text Generation</option>
          <option value="question_answering">Question Answering</option>
        </select>
      </div>

      <!-- Translation Target -->
      <div v-if="taskType === 'translation'" class="mb-4">
        <label class="block text-sm text-gray-400 mb-2">Target Language</label>
        <select v-model="targetLang" class="w-full bg-gray-700 rounded px-4 py-2">
          <option value="fr">French</option>
          <option value="de">German</option>
          <option value="es">Spanish</option>
          <option value="ru">Russian</option>
        </select>
      </div>

      <!-- Context for Q&A -->
      <div v-if="taskType === 'question_answering'" class="mb-4">
        <label class="block text-sm text-gray-400 mb-2">Context (the text to search for answers)</label>
        <textarea
          v-model="context"
          class="w-full bg-gray-700 rounded px-4 py-2 h-32"
          placeholder="Enter the context text that contains the answers..."
        ></textarea>
      </div>

      <!-- Input Items -->
      <div class="mb-4">
        <label class="block text-sm text-gray-400 mb-2">
          {{ getInputLabel() }}
        </label>
        <textarea
          v-model="inputText"
          class="w-full bg-gray-700 rounded px-4 py-2 h-48 font-mono text-sm"
          :placeholder="getInputPlaceholder()"
        ></textarea>
        <div class="text-xs text-gray-500 mt-1">One item per line</div>
      </div>

      <!-- Chunk Size -->
      <div class="mb-6">
        <label class="block text-sm text-gray-400 mb-2">Chunk Size</label>
        <input
          v-model.number="chunkSize"
          type="number"
          min="1"
          max="100"
          class="w-24 bg-gray-700 rounded px-4 py-2"
        />
        <span class="text-xs text-gray-500 ml-2">Items per chunk (1-100)</span>
      </div>

      <!-- Submit Button -->
      <button
        @click="submitJob"
        :disabled="loading || !inputText.trim()"
        class="w-full py-3 rounded-lg font-semibold transition-colors"
        :class="loading ? 'bg-gray-600 cursor-wait' : 'bg-green-600 hover:bg-green-700'"
      >
        {{ loading ? 'Submitting...' : 'Submit Job' }}
      </button>

      <!-- Result -->
      <div v-if="result" class="mt-4 p-4 rounded" :class="result.success ? 'bg-green-900' : 'bg-red-900'">
        <div class="font-semibold">{{ result.success ? 'Job Created!' : 'Error' }}</div>
        <div class="text-sm mt-1">{{ result.message }}</div>
        <div v-if="result.jobId" class="font-mono text-xs mt-2">Job ID: {{ result.jobId }}</div>
      </div>
    </div>

    <!-- Examples -->
    <div class="mt-6 bg-gray-800 rounded-lg border border-gray-700 p-6">
      <h2 class="text-lg font-semibold mb-4">Examples</h2>

      <div class="space-y-4 text-sm">
        <div>
          <div class="text-gray-400">Sentiment Analysis:</div>
          <code class="text-green-400">I love this product!
This is terrible
It's okay, nothing special</code>
        </div>

        <div>
          <div class="text-gray-400">Translation:</div>
          <code class="text-green-400">Hello, how are you?
The weather is nice today
I am learning to code</code>
        </div>

        <div>
          <div class="text-gray-400">Image Classification:</div>
          <code class="text-green-400">https://example.com/cat.jpg
https://example.com/dog.jpg</code>
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
      taskType: 'sentiment_analysis',
      targetLang: 'fr',
      inputText: '',
      context: '',
      chunkSize: 5,
      loading: false,
      result: null
    }
  },
  methods: {
    getInputLabel() {
      const labels = {
        'sentiment_analysis': 'Texts to Analyze',
        'translation': 'Texts to Translate',
        'summarization': 'Texts to Summarize',
        'image_classification': 'Image URLs',
        'text_generation': 'Prompts',
        'question_answering': 'Questions',
      }
      return labels[this.taskType] || 'Input Items'
    },
    getInputPlaceholder() {
      const placeholders = {
        'sentiment_analysis': 'Great product!\nTerrible experience\nIt was okay',
        'translation': 'Hello world\nHow are you?',
        'summarization': 'Long text to summarize...',
        'image_classification': 'https://example.com/image1.jpg\nhttps://example.com/image2.jpg',
        'text_generation': 'Once upon a time\nThe future of AI is',
        'question_answering': 'What is the capital?\nWho invented this?',
      }
      return placeholders[this.taskType] || 'Enter items, one per line'
    },
    async submitJob() {
      this.loading = true
      this.result = null

      try {
        const items = this.inputText.split('\n').filter(line => line.trim())

        if (items.length === 0) {
          this.result = { success: false, message: 'Please enter at least one item' }
          return
        }

        const payload = { items }

        // Add task-specific fields
        if (this.taskType === 'translation') {
          payload.target = this.targetLang
        }
        if (this.taskType === 'question_answering') {
          payload.context = this.context
        }

        const res = await axios.post('/jobs-api/jobs', {
          task_type: this.taskType,
          payload,
          chunk_size: this.chunkSize
        })

        this.result = {
          success: true,
          message: `Job submitted with ${res.data.total_chunks} chunks`,
          jobId: res.data.job_id
        }

        // Clear form
        this.inputText = ''

      } catch (e) {
        this.result = {
          success: false,
          message: e.response?.data?.detail || e.message
        }
      } finally {
        this.loading = false
      }
    }
  }
}
</script>
