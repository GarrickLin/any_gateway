import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/admin': 'http://localhost:8003',
      '/user': 'http://localhost:8003',
      '/auth': 'http://localhost:8003',
      '/v1': 'http://localhost:8003',
    },
  },
  build: {
    outDir: 'dist',
  },
})
