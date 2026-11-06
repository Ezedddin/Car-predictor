import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// /api wordt doorgestuurd naar de FastAPI-server (app/api), zodat de frontend geen CORS nodig heeft
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
