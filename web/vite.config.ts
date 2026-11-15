import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Relative base so the static build works from any path (e.g. a Vercel backup link).
export default defineConfig({
  base: './',
  plugins: [react()],
  define: { __BUILD_DATE__: JSON.stringify(new Date().toISOString().slice(0, 10)) },
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
})
