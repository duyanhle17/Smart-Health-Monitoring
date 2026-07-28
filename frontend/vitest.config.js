import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Kept separate from vite.config.js so the production build config is never
// touched by test setup. Globals stay off; test files import from 'vitest'
// explicitly, which keeps the existing eslint config working unchanged.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
  },
})
