<template>
  <div class="max-w-2xl">
    <h1 class="text-2xl font-bold mb-6">Create Task</h1>

    <div class="bg-gray-800 rounded-lg border border-gray-700 p-6">
      <!-- Task Type -->
      <div class="mb-4">
        <label class="block text-sm text-gray-400 mb-2">Task Type</label>
        <select v-model="taskType" class="w-full bg-gray-700 rounded px-4 py-2">
          <option value="text">Text Processing</option>
          <option value="reverse">Text Reverse</option>
          <option value="math">Math Calculation</option>
          <option value="sentiment">Sentiment Analysis</option>
          <option value="classification">Classification</option>
          <option value="extraction">Data Extraction</option>
        </select>
      </div>

      <!-- Prompt/Input -->
      <div class="mb-4">
        <label class="block text-sm text-gray-400 mb-2">Prompt / Input</label>
        <textarea
          v-model="prompt"
          class="w-full bg-gray-700 rounded px-4 py-2 h-32"
          :placeholder="getPlaceholder()"
        ></textarea>
      </div>

      <!-- Expected Answer (for golden tasks) -->
      <div class="mb-4">
        <label class="flex items-center space-x-2 cursor-pointer">
          <input type="checkbox" v-model="isGoldenTask" class="rounded bg-gray-700">
          <span class="text-sm text-gray-400">Create as Golden Task (honeypot with known answer)</span>
        </label>
      </div>

      <div v-if="isGoldenTask" class="mb-4">
        <label class="block text-sm text-gray-400 mb-2">Expected Answer</label>
        <input
          v-model="expectedAnswer"
          class="w-full bg-gray-700 rounded px-4 py-2"
          placeholder="The correct answer for this task"
        />
      </div>

      <!-- Reward -->
      <div class="mb-6">
        <label class="block text-sm text-gray-400 mb-2">Reward (tokens)</label>
        <input
          v-model.number="reward"
          type="number"
          step="0.01"
          min="0.01"
          class="w-32 bg-gray-700 rounded px-4 py-2"
        />
        <span class="text-xs text-gray-500 ml-2">Default rewards: text=0.05, math=0.15, sentiment=0.05</span>
      </div>

      <!-- Submit Button -->
      <button
        @click="createTask"
        :disabled="loading || !prompt.trim()"
        class="w-full py-3 rounded-lg font-semibold transition-colors"
        :class="loading ? 'bg-gray-600 cursor-wait' : 'bg-green-600 hover:bg-green-700'"
      >
        {{ loading ? 'Creating...' : 'Create Task' }}
      </button>

      <!-- Result -->
      <div v-if="result" class="mt-4 p-4 rounded" :class="result.success ? 'bg-green-900' : 'bg-red-900'">
        <div class="font-semibold">{{ result.success ? 'Task Created!' : 'Error' }}</div>
        <div class="text-sm mt-1">{{ result.message }}</div>
      </div>
    </div>

    <!-- Bulk Create -->
    <div class="mt-6 bg-gray-800 rounded-lg border border-gray-700 p-6">
      <h2 class="text-lg font-semibold mb-4">Bulk Create Tasks</h2>
      <p class="text-sm text-gray-400 mb-4">Create multiple tasks at once. One prompt per line.</p>

      <div class="mb-4">
        <label class="block text-sm text-gray-400 mb-2">Task Type</label>
        <select v-model="bulkTaskType" class="w-full bg-gray-700 rounded px-4 py-2">
          <option value="text">Text Processing</option>
          <option value="reverse">Text Reverse</option>
          <option value="math">Math Calculation</option>
          <option value="sentiment">Sentiment Analysis</option>
        </select>
      </div>

      <div class="mb-4">
        <label class="block text-sm text-gray-400 mb-2">Prompts (one per line)</label>
        <textarea
          v-model="bulkPrompts"
          class="w-full bg-gray-700 rounded px-4 py-2 h-48 font-mono text-sm"
          placeholder="reverse this text
calculate 2+2
analyze sentiment: I love this
another task..."
        ></textarea>
      </div>

      <button
        @click="createBulkTasks"
        :disabled="bulkLoading || !bulkPrompts.trim()"
        class="w-full py-3 rounded-lg font-semibold transition-colors"
        :class="bulkLoading ? 'bg-gray-600 cursor-wait' : 'bg-blue-600 hover:bg-blue-700'"
      >
        {{ bulkLoading ? 'Creating...' : 'Create All Tasks' }}
      </button>

      <div v-if="bulkResult" class="mt-4 p-4 rounded" :class="bulkResult.success ? 'bg-green-900' : 'bg-red-900'">
        <div class="font-semibold">{{ bulkResult.message }}</div>
      </div>
    </div>

    <!-- Recent Tasks -->
    <div class="mt-6 bg-gray-800 rounded-lg border border-gray-700 p-6">
      <div class="flex justify-between items-center mb-4">
        <h2 class="text-lg font-semibold">Recent Tasks</h2>
        <button @click="loadRecentTasks" class="text-sm text-blue-400 hover:text-blue-300">
          Refresh
        </button>
      </div>

      <div class="space-y-2">
        <div
          v-for="task in recentTasks"
          :key="task.id"
          class="flex justify-between items-center p-3 bg-gray-900 rounded"
        >
          <div>
            <span class="font-mono text-sm text-gray-400">#{{ task.id }}</span>
            <span class="ml-2 text-sm">{{ task.prompt?.substring(0, 50) }}{{ task.prompt?.length > 50 ? '...' : '' }}</span>
          </div>
          <div class="flex items-center space-x-2">
            <button
              v-if="task.status === 'pending'"
              @click="simulateProcess(task.id)"
              class="px-2 py-1 bg-green-600 hover:bg-green-700 rounded text-xs"
            >
              Process
            </button>
            <span :class="getStatusClass(task.status)" class="px-2 py-1 rounded text-xs">
              {{ task.status }}
            </span>
          </div>
        </div>
        <div v-if="recentTasks.length === 0" class="text-center text-gray-500 py-4">
          No tasks yet
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
      // Single task
      taskType: 'text',
      prompt: '',
      isGoldenTask: false,
      expectedAnswer: '',
      reward: 0.05,
      loading: false,
      result: null,

      // Bulk tasks
      bulkTaskType: 'text',
      bulkPrompts: '',
      bulkLoading: false,
      bulkResult: null,

      // Recent tasks
      recentTasks: []
    }
  },
  async mounted() {
    await this.loadRecentTasks()
  },
  methods: {
    getPlaceholder() {
      const placeholders = {
        'text': 'Enter text to process...',
        'reverse': 'Enter text to reverse...',
        'math': 'Enter math expression: 2 + 2',
        'sentiment': 'Enter text to analyze sentiment...',
        'classification': 'Enter text to classify...',
        'extraction': 'Enter text to extract data from...'
      }
      return placeholders[this.taskType] || 'Enter prompt...'
    },

    async createTask() {
      this.loading = true
      this.result = null

      try {
        const payload = {
          prompt: this.prompt,
          task_type: this.taskType
        }

        // Create regular task
        const res = await axios.post('/api/tasks/create', payload)

        this.result = {
          success: true,
          message: `Task #${res.data.task_id} created successfully!`
        }

        // If golden task, also create the golden task entry
        if (this.isGoldenTask && this.expectedAnswer) {
          try {
            await axios.post('/api/admin/golden-tasks', {
              prompt: this.prompt,
              task_type: this.taskType,
              expected_answer: this.expectedAnswer
            })
            this.result.message += ' (Added as golden task)'
          } catch (e) {
            this.result.message += ' (Warning: Failed to add as golden task)'
          }
        }

        // Clear form
        this.prompt = ''
        this.expectedAnswer = ''
        this.isGoldenTask = false

        // Refresh recent tasks
        await this.loadRecentTasks()

      } catch (e) {
        this.result = {
          success: false,
          message: e.response?.data?.detail || e.message
        }
      } finally {
        this.loading = false
      }
    },

    async createBulkTasks() {
      this.bulkLoading = true
      this.bulkResult = null

      try {
        const prompts = this.bulkPrompts.split('\n').filter(line => line.trim())

        if (prompts.length === 0) {
          this.bulkResult = { success: false, message: 'No prompts provided' }
          return
        }

        let created = 0
        let failed = 0

        for (const prompt of prompts) {
          try {
            await axios.post('/api/tasks/create', {
              prompt: prompt.trim(),
              task_type: this.bulkTaskType
            })
            created++
          } catch (e) {
            failed++
          }
        }

        this.bulkResult = {
          success: failed === 0,
          message: `Created ${created} tasks` + (failed > 0 ? `, ${failed} failed` : '')
        }

        // Clear form
        this.bulkPrompts = ''

        // Refresh recent tasks
        await this.loadRecentTasks()

      } catch (e) {
        this.bulkResult = {
          success: false,
          message: e.message
        }
      } finally {
        this.bulkLoading = false
      }
    },

    async loadRecentTasks() {
      try {
        const res = await axios.get('/api/tasks/?limit=10')
        this.recentTasks = res.data.tasks || res.data || []
      } catch (e) {
        console.error('Failed to load recent tasks:', e)
      }
    },

    getStatusClass(status) {
      const classes = {
        'pending': 'bg-yellow-900 text-yellow-300',
        'assigned': 'bg-blue-900 text-blue-300',
        'submitted_A': 'bg-purple-900 text-purple-300',
        'validating': 'bg-indigo-900 text-indigo-300',
        'done': 'bg-green-900 text-green-300',
        'rejected': 'bg-red-900 text-red-300',
      }
      return classes[status] || 'bg-gray-700 text-gray-400'
    },

    async simulateProcess(taskId) {
      try {
        // Ensure we have 2 workers
        let workers = []
        try {
          const res = await axios.get('/api/workers/')
          workers = res.data.workers || res.data || []
        } catch (e) {
          workers = []
        }

        // Create workers if needed
        if (workers.length < 2) {
          await axios.post('/api/workers/register', { name: 'AutoWorker1', power: 50 })
          await axios.post('/api/workers/register', { name: 'AutoWorker2', power: 50 })
          const res = await axios.get('/api/workers/')
          workers = res.data.workers || res.data || []
        }

        const worker1 = workers[0]?.id || 1
        const worker2 = workers[1]?.id || 2

        // Worker 1 gets task
        await axios.get(`/api/tasks/next/${worker1}`)

        // Worker 1 submits
        await axios.post('/api/tasks/submit', {
          task_id: taskId,
          worker_id: worker1,
          result: 'auto-processed-result'
        })

        // Worker 2 gets validation task
        await axios.get(`/api/tasks/next/${worker2}`)

        // Worker 2 validates
        await axios.post('/api/tasks/validate', {
          task_id: taskId,
          worker_id: worker2,
          result: 'auto-processed-result'
        })

        // Refresh
        await this.loadRecentTasks()

      } catch (e) {
        alert('Failed to process: ' + (e.response?.data?.detail || e.message))
        await this.loadRecentTasks()
      }
    }
  }
}
</script>
