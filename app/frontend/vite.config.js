import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// /api wordt doorgestuurd naar de FastAPI-server (app/api), zodat de frontend geen CORS nodig heeft
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
