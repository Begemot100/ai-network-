<template>
  <div>
    <h1 class="text-2xl font-bold mb-6">Dashboard</h1>

    <!-- Stats Cards -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
      <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <div class="text-gray-400 text-sm">Total Workers</div>
        <div class="text-3xl font-bold text-blue-400">{{ stats.workers?.total || 0 }}</div>
        <div class="text-sm text-gray-500">{{ stats.workers?.active || 0 }} active</div>
      </div>

      <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <div class="text-gray-400 text-sm">Tasks Completed</div>
        <div class="text-3xl font-bold text-green-400">{{ stats.tasks?.done || 0 }}</div>
        <div class="text-sm text-gray-500">{{ stats.tasks?.pending || 0 }} pending</div>
      </div>

      <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <div class="text-gray-400 text-sm">Total Earned</div>
        <div class="text-3xl font-bold text-yellow-400">{{ formatTokens(stats.financial?.total_earned) }}</div>
        <div class="text-sm text-gray-500">tokens distributed</div>
      </div>

      <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <div class="text-gray-400 text-sm">Avg Reputation</div>
        <div class="text-3xl font-bold text-purple-400">{{ (stats.workers?.avg_reputation || 0).toFixed(2) }}</div>
        <div class="text-sm text-gray-500">across all workers</div>
      </div>
    </div>

    <!-- System Stats -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <!-- Processing Stats -->
      <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h2 class="text-lg font-semibold mb-4">Processing Stats</h2>
        <div class="space-y-3">
          <div class="flex justify-between">
            <span class="text-gray-400">Tasks Last Hour</span>
            <span class="font-mono">{{ systemStats.processing?.tasks_last_hour || 0 }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-gray-400">Tasks Last Day</span>
            <span class="font-mono">{{ systemStats.processing?.tasks_last_day || 0 }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-gray-400">Tasks/Minute</span>
            <span class="font-mono">{{ (systemStats.processing?.tasks_per_minute || 0).toFixed(2) }}</span>
          </div>
        </div>
      </div>

      <!-- Quality Stats -->
      <div class="bg-gray-800 rounded-lg p-6 border border-gray-700">
        <h2 class="text-lg font-semibold mb-4">Quality Metrics</h2>
        <div class="space-y-3">
          <div class="flex justify-between">
            <span class="text-gray-400">Validated Tasks</span>
            <span class="font-mono text-green-400">{{ systemStats.quality?.total_validated || 0 }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-gray-400">Rejected</span>
            <span class="font-mono text-red-400">{{ systemStats.quality?.rejected || 0 }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-gray-400">Rejection Rate</span>
            <span class="font-mono">{{ ((systemStats.quality?.rejection_rate || 0) * 100).toFixed(1) }}%</span>
          </div>
          <div class="flex justify-between">
            <span class="text-gray-400">Golden Task Pass Rate</span>
            <span class="font-mono text-yellow-400">{{ systemStats.golden_tasks?.pass_rate || 0 }}%</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Recent Activity -->
    <div class="mt-6 bg-gray-800 rounded-lg p-6 border border-gray-700">
      <h2 class="text-lg font-semibold mb-4">Recent Audit Log</h2>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left text-gray-400 border-b border-gray-700">
              <th class="pb-2">Time</th>
              <th class="pb-2">Action</th>
              <th class="pb-2">Worker</th>
              <th class="pb-2">Details</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in auditLogs" :key="log.id" class="border-b border-gray-700">
              <td class="py-2 text-gray-400">{{ formatTime(log.created_at) }}</td>
              <td class="py-2">
                <span :class="getActionClass(log.action)">{{ log.action }}</span>
              </td>
              <td class="py-2">{{ log.worker_id || '-' }}</td>
              <td class="py-2 text-gray-400">{{ log.details || '-' }}</td>
            </tr>
            <tr v-if="auditLogs.length === 0">
              <td colspan="4" class="py-4 text-center text-gray-500">No recent activity</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios'

export default {
  data() {
    return {
      stats: {},
      systemStats: {},
      auditLogs: []
    }
  },
  async mounted() {
    await this.loadData()
    setInterval(this.loadData, 5000)
  },
  methods: {
    async loadData() {
      try {
        const [dashboard, system, audit] = await Promise.all([
          axios.get('/api/admin/dashboard'),
          axios.get('/api/admin/system-stats'),
          axios.get('/api/admin/audit-log?limit=10')
        ])
        this.stats = dashboard.data
        this.systemStats = system.data
        this.auditLogs = audit.data.logs || []
      } catch (e) {
        console.error('Failed to load dashboard:', e)
      }
    },
    formatTokens(val) {
      return (val || 0).toFixed(2)
    },
    formatTime(ts) {
      if (!ts) return '-'
      return new Date(ts).toLocaleTimeString()
    },
    getActionClass(action) {
      const classes = {
        'task_create': 'text-blue-400',
        'task_submit': 'text-yellow-400',
        'task_validate': 'text-green-400',
        'worker_register': 'text-purple-400',
        'worker_ban': 'text-red-400',
        'fraud_detected': 'text-red-500 font-bold',
      }
      return classes[action] || 'text-gray-300'
    }
  }
}
</script>
