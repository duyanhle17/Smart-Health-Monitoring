import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': process.env.VITE_BACKEND_URL || 'http://localhost:5000',
      '/latest_status': process.env.VITE_BACKEND_URL || 'http://localhost:5000',
      '/socket.io': {
        target: process.env.VITE_BACKEND_URL || 'http://localhost:5000',
        ws: true
      }
    }
  }
})
