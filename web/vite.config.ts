import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Relative base so the static build works from any path (e.g. a Vercel backup link).
export default defineConfig({
  base: './',
  plugins: [react()],
})
