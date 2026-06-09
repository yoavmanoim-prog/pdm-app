import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Tells Vite to use the React plugin so it understands JSX syntax
export default defineConfig({
  plugins: [react()],
  build: { outDir: 'dist' },
  server: {
    // dev: proxy /api/ → local backend so CORS is not an issue
    proxy: {
      '/api': {
        // LOCAL_VAULT_URL is set to http://local-vault:8000 in docker-compose
        // so the Vite dev server can reach the backend container by service name
        target: process.env.LOCAL_VAULT_URL || 'http://localhost:8000',
        changeOrigin: true,
        rewrite: path => path.replace(/^\/api/, '')
      }
    }
  }
})
