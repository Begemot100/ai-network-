<template>
  <div>
    <div class="flex justify-between items-center mb-6">
      <h1 class="text-2xl font-bold">Workers</h1>
      <button @click="loadWorkers" class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg text-sm">
        Refresh
      </button>
    </div>

    <!-- Workers Table -->
    <div class="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-gray-750">
          <tr class="text-left text-gray-400 border-b border-gray-700">
            <th class="px-4 py-3">ID</th>
            <th class="px-4 py-3">Name</th>
            <th class="px-4 py-3">Status</th>
            <th class="px-4 py-3">Reputation</th>
            <th class="px-4 py-3">Balance</th>
            <th class="px-4 py-3">Tasks Done</th>
            <th class="px-4 py-3">Last Seen</th>
            <th class="px-4 py-3">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="worker in workers" :key="worker.id" class="border-b border-gray-700 hover:bg-gray-750">
            <td class="px-4 py-3 font-mono">{{ worker.id }}</td>
            <td class="px-4 py-3">{{ worker.name }}</td>
            <td class="px-4 py-3">
              <span :class="getStatusClass(worker.status)" class="px-2 py-1 rounded text-xs">
                {{ worker.status }}
              </span>
            </td>
            <td class="px-4 py-3">
              <div class="flex items-center">
                <div class="w-16 bg-gray-700 rounded-full h-2 mr-2">
                  <div
                    class="h-2 rounded-full"
                    :class="getReputationColor(worker.reputation)"
                    :style="{ width: Math.min(worker.reputation * 10, 100) + '%' }"
                  ></div>
                </div>
                <span class="font-mono text-sm">{{ worker.reputation?.toFixed(2) }}</span>
              </div>
            </td>
            <td class="px-4 py-3 font-mono text-yellow-400">{{ worker.balance?.toFixed(4) }}</td>
            <td class="px-4 py-3 font-mono">{{ worker.tasks_completed || 0 }}</td>
            <td class="px-4 py-3 text-gray-400 text-xs">{{ formatTime(worker.last_seen) }}</td>
            <td class="px-4 py-3">
              <button
                v-if="worker.status !== 'banned'"
                @click="banWorker(worker.id)"
                class="text-red-400 hover:text-red-300 text-xs"
              >
                Ban
              </button>
              <button
                v-else
                @click="unbanWorker(worker.id)"
                class="text-green-400 hover:text-green-300 text-xs"
              >
                Unban
              </button>
            </td>
          </tr>
          <tr v-if="workers.length === 0">
            <td colspan="8" class="px-4 py-8 text-center text-gray-500">
              No workers registered yet
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Worker Stats -->
    <div class="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4">
      <div class="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <div class="text-gray-400 text-sm">Total Workers</div>
        <div class="text-2xl font-bold">{{ workers.length }}</div>
      </div>
      <div class="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <div class="text-gray-400 text-sm">Active Workers</div>
        <div class="text-2xl font-bold text-green-400">
          {{ workers.filter(w => w.status === 'idle' || w.status === 'working').length }}
        </div>
      </div>
      <div class="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <div class="text-gray-400 text-sm">Banned Workers</div>
        <div class="text-2xl font-bold text-red-400">
          {{ workers.filter(w => w.status === 'banned').length }}
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
      workers: []
    }
  },
  async mounted() {
    await this.loadWorkers()
  },
  methods: {
    async loadWorkers() {
      try {
        const res = await axios.get('/api/workers/')
        this.workers = res.data.workers || res.data || []
      } catch (e) {
        console.error('Failed to load workers:', e)
      }
    },
    async banWorker(workerId) {
      if (!confirm('Are you sure you want to ban this worker?')) return
      try {
        await axios.post(`/api/admin/ban?worker_id=${workerId}&reason=Admin action`)
        await this.loadWorkers()
      } catch (e) {
        alert('Failed to ban worker: ' + e.message)
      }
    },
    async unbanWorker(workerId) {
      try {
        await axios.post(`/api/admin/unban?worker_id=${workerId}`)
        await this.loadWorkers()
      } catch (e) {
        alert('Failed to unban worker: ' + e.message)
      }
    },
    getStatusClass(status) {
      const classes = {
        'idle': 'bg-green-900 text-green-300',
        'working': 'bg-blue-900 text-blue-300',
        'offline': 'bg-gray-700 text-gray-400',
        'banned': 'bg-red-900 text-red-300',
      }
      return classes[status] || 'bg-gray-700 text-gray-400'
    },
    getReputationColor(rep) {
      if (rep >= 3) return 'bg-green-500'
      if (rep >= 1.5) return 'bg-yellow-500'
      return 'bg-red-500'
    },
    formatTime(ts) {
      if (!ts) return 'Never'
      return new Date(ts).toLocaleString()
    }
  }
}
</script>
