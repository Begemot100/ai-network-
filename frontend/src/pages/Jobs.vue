<template>
  <div>
    <div class="flex justify-between items-center mb-6">
      <h1 class="text-2xl font-bold">Batch Jobs</h1>
      <div class="flex space-x-2">
        <router-link to="/jobs/new" class="bg-green-600 hover:bg-green-700 px-4 py-2 rounded-lg text-sm">
          + New Job
        </router-link>
        <button @click="loadJobs" class="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg text-sm">
          Refresh
        </button>
      </div>
    </div>

    <!-- Jobs List -->
    <div class="space-y-4">
      <div v-for="job in jobs" :key="job.job_id" class="bg-gray-800 rounded-lg border border-gray-700 p-4">
        <div class="flex justify-between items-start">
          <div>
            <div class="font-mono text-sm text-gray-400">{{ job.job_id }}</div>
            <div class="flex items-center space-x-3 mt-2">
              <span :class="getStatusClass(job.status)" class="px-2 py-1 rounded text-xs">
                {{ job.status }}
              </span>
              <span class="text-gray-400 text-sm">
                {{ job.completed_chunks }}/{{ job.total_chunks }} chunks
              </span>
            </div>
          </div>
          <div class="text-right">
            <div class="text-sm text-gray-400">Progress</div>
            <div class="text-xl font-bold">
              {{ Math.round((job.completed_chunks / job.total_chunks) * 100) }}%
            </div>
          </div>
        </div>

        <!-- Progress Bar -->
        <div class="mt-4 w-full bg-gray-700 rounded-full h-2">
          <div
            class="h-2 rounded-full transition-all duration-500"
            :class="job.status === 'done' ? 'bg-green-500' : 'bg-blue-500'"
            :style="{ width: (job.completed_chunks / job.total_chunks * 100) + '%' }"
          ></div>
        </div>

        <!-- Actions -->
        <div class="mt-4 flex space-x-2">
          <button
            @click="viewResults(job.job_id)"
            :disabled="job.status !== 'done'"
            class="text-sm px-3 py-1 rounded"
            :class="job.status === 'done' ? 'bg-blue-600 hover:bg-blue-700' : 'bg-gray-700 text-gray-500 cursor-not-allowed'"
          >
            View Results
          </button>
          <button
            v-if="job.status === 'running'"
            @click="cancelJob(job.job_id)"
            class="text-sm px-3 py-1 rounded bg-red-600 hover:bg-red-700"
          >
            Cancel
          </button>
        </div>

        <!-- Results Preview -->
        <div v-if="selectedJob === job.job_id && results" class="mt-4 bg-gray-900 rounded p-4">
          <h4 class="text-sm font-semibold mb-2">Results:</h4>
          <pre class="text-xs overflow-auto max-h-64">{{ JSON.stringify(results, null, 2) }}</pre>
        </div>
      </div>

      <div v-if="jobs.length === 0" class="bg-gray-800 rounded-lg border border-gray-700 p-8 text-center">
        <div class="text-gray-500">No batch jobs yet</div>
        <router-link to="/jobs/new" class="text-blue-400 hover:text-blue-300 text-sm">
          Create your first job
        </router-link>
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios'

export default {
  data() {
    return {
      jobs: [],
      selectedJob: null,
      results: null
    }
  },
  async mounted() {
    await this.loadJobs()
    setInterval(this.loadJobs, 3000)
  },
  methods: {
    async loadJobs() {
      try {
        // Get jobs from database
        const res = await axios.get('/api/admin/dashboard')
        // For now, we'll store jobs locally since there's no list endpoint
        // In production, you'd add a /jobs endpoint
      } catch (e) {
        console.error('Failed to load jobs:', e)
      }
    },
    async viewResults(jobId) {
      try {
        this.selectedJob = jobId
        const res = await axios.get(`/jobs-api/jobs/${jobId}/results`)
        this.results = res.data
      } catch (e) {
        alert('Failed to load results: ' + e.message)
      }
    },
    async cancelJob(jobId) {
      try {
        await axios.post(`/jobs-api/jobs/${jobId}/cancel`)
        await this.loadJobs()
      } catch (e) {
        alert('Failed to cancel job: ' + e.message)
      }
    },
    getStatusClass(status) {
      const classes = {
        'pending': 'bg-yellow-900 text-yellow-300',
        'running': 'bg-blue-900 text-blue-300',
        'done': 'bg-green-900 text-green-300',
        'failed': 'bg-red-900 text-red-300',
        'cancelled': 'bg-gray-700 text-gray-400',
      }
      return classes[status] || 'bg-gray-700 text-gray-400'
    }
  }
}
</script>
