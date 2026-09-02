import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { mockApiPlugin } from './vite-mock-plugin.js'

export default defineConfig({
  plugins: [react(), mockApiPlugin()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
