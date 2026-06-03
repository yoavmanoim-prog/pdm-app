import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Tells Vite to use the React plugin so it understands JSX syntax
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist' // output folder — nginx will serve files from here
  }
})
