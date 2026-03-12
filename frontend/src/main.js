import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './style.css'

// Pages
import Dashboard from './pages/Dashboard.vue'
import Workers from './pages/Workers.vue'
import Tasks from './pages/Tasks.vue'
import CreateTask from './pages/CreateTask.vue'
import Jobs from './pages/Jobs.vue'
import NewJob from './pages/NewJob.vue'
import Playground from './pages/Playground.vue'

const routes = [
  { path: '/', component: Dashboard, name: 'Dashboard' },
  { path: '/workers', component: Workers, name: 'Workers' },
  { path: '/tasks', component: Tasks, name: 'Tasks' },
  { path: '/tasks/create', component: CreateTask, name: 'CreateTask' },
  { path: '/jobs', component: Jobs, name: 'Jobs' },
  { path: '/jobs/new', component: NewJob, name: 'NewJob' },
  { path: '/playground', component: Playground, name: 'Playground' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

createApp(App).use(router).mount('#app')
