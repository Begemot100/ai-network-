<template>
  <div>
    <div class="flex justify-between items-center mb-6">
      <h1 class="text-2xl font-bold">Tasks</h1>
      <div class="flex space-x-2">
        <select v-model="filter" @change="loadTasks" class="bg-gray-700 rounded px-3 py-2 text-sm">
          <option value="all">All Tasks</option>
          <option value="pending">Pending</option>
          <option value="done">Completed</option>
          <option value="rejected">Rejected</option>
        </select>
        <button @click="loadTasks" class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg text-sm">
          Refresh
        </button>
      </div>
    </div>

    <!-- Task Stats -->
    <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
      <div class="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <div class="text-gray-400 text-xs">Pending</div>
        <div class="text-xl font-bold text-yellow-400">{{ stats.pending || 0 }}</div>
      </div>
      <div class="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <div class="text-gray-400 text-xs">Assigned</div>
        <div class="text-xl font-bold text-blue-400">{{ stats.assigned || 0 }}</div>
      </div>
      <div class="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <div class="text-gray-400 text-xs">Validating</div>
        <div class="text-xl font-bold text-purple-400">{{ stats.validating || 0 }}</div>
      </div>
      <div class="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <div class="text-gray-400 text-xs">Done</div>
        <div class="text-xl font-bold text-green-400">{{ stats.done || 0 }}</div>
      </div>
      <div class="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <div class="text-gray-400 text-xs">Rejected</div>
        <div class="text-xl font-bold text-red-400">{{ stats.rejected || 0 }}</div>
      </div>
    </div>

    <!-- Tasks Table -->
    <div class="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-left text-gray-400 border-b border-gray-700">
            <th class="px-4 py-3">ID</th>
            <th class="px-4 py-3">Type</th>
            <th class="px-4 py-3">Prompt</th>
            <th class="px-4 py-3">Status</th>
            <th class="px-4 py-3">Worker A</th>
            <th class="px-4 py-3">Worker B</th>
            <th class="px-4 py-3">Reward</th>
            <th class="px-4 py-3">Created</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="task in tasks" :key="task.id" class="border-b border-gray-700 hover:bg-gray-750">
            <td class="px-4 py-3 font-mono">{{ task.id }}</td>
            <td class="px-4 py-3">
              <span class="px-2 py-1 bg-gray-700 rounded text-xs">{{ task.task_type }}</span>
            </td>
            <td class="px-4 py-3 max-w-xs truncate" :title="task.prompt">{{ task.prompt }}</td>
            <td class="px-4 py-3">
              <span :class="getStatusClass(task.status)" class="px-2 py-1 rounded text-xs">
                {{ task.status }}
              </span>
            </td>
            <td class="px-4 py-3">{{ task.worker_id || '-' }}</td>
            <td class="px-4 py-3">{{ task.validator_worker_id || '-' }}</td>
            <td class="px-4 py-3 font-mono text-yellow-400">{{ task.reward?.toFixed(2) || '0.00' }}</td>
            <td class="px-4 py-3 text-gray-400 text-xs">{{ formatTime(task.created_at) }}</td>
          </tr>
          <tr v-if="tasks.length === 0">
            <td colspan="8" class="px-4 py-8 text-center text-gray-500">
              No tasks found
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script>
import axios from 'axios'

export default {
  data() {
    return {
      tasks: [],
      stats: {},
      filter: 'all'
    }
  },
  async mounted() {
    await this.loadTasks()
    await this.loadStats()
  },
  methods: {
    async loadTasks() {
      try {
        const params = this.filter !== 'all' ? `?status=${this.filter}` : ''
        const res = await axios.get(`/api/tasks/${params}`)
        this.tasks = res.data.tasks || res.data || []
      } catch (e) {
        console.error('Failed to load tasks:', e)
      }
    },
    async loadStats() {
      try {
        const res = await axios.get('/api/tasks/stats')
        this.stats = res.data
      } catch (e) {
        console.error('Failed to load stats:', e)
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
    formatTime(ts) {
      if (!ts) return '-'
      return new Date(ts).toLocaleString()
    }
  }
}
</script>
