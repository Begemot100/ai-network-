import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const API_URL = process.env.API_URL || 'http://localhost:8050'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: API_URL,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      },
      '/ws': {
        target: API_URL.replace('http', 'ws'),
        ws: true,
      }
    }
  }
})
