<template>
  <div class="min-h-screen bg-gray-900">
    <!-- Navigation -->
    <nav class="bg-gray-800 border-b border-gray-700">
      <div class="max-w-7xl mx-auto px-4">
        <div class="flex items-center justify-between h-16">
          <div class="flex items-center">
            <span class="text-xl font-bold text-green-400">AI Network</span>
            <div class="ml-10 flex space-x-4">
              <router-link
                v-for="link in navLinks"
                :key="link.path"
                :to="link.path"
                class="px-3 py-2 rounded-md text-sm font-medium transition-colors"
                :class="$route.path === link.path ? 'bg-gray-900 text-white' : 'text-gray-300 hover:bg-gray-700'"
              >
                {{ link.name }}
              </router-link>
            </div>
          </div>
          <div class="flex items-center space-x-4">
            <span class="text-sm text-gray-400">Status:</span>
            <span :class="serverStatus ? 'text-green-400' : 'text-red-400'">
              {{ serverStatus ? 'Online' : 'Offline' }}
            </span>
          </div>
        </div>
      </div>
    </nav>

    <!-- Main Content -->
    <main class="max-w-7xl mx-auto px-4 py-6">
      <router-view />
    </main>
  </div>
</template>

<script>
import axios from 'axios'

export default {
  data() {
    return {
      serverStatus: false,
      navLinks: [
        { path: '/', name: 'Dashboard' },
        { path: '/workers', name: 'Workers' },
        { path: '/tasks', name: 'Tasks' },
        { path: '/playground', name: 'AI Playground' },
        { path: '/jobs', name: 'Batch Jobs' },
      ]
    }
  },
  async mounted() {
    await this.checkStatus()
    setInterval(this.checkStatus, 10000)
  },
  methods: {
    async checkStatus() {
      try {
        await axios.get('/api/health')
        this.serverStatus = true
      } catch {
        this.serverStatus = false
      }
    }
  }
}
</script>
