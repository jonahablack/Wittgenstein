import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Forward API calls to the Flask dev server (`python3 app.py`, port 3000)
    // so `npm run dev` gives hot-reload on :5173 without needing a rebuild.
    proxy: {
      '/upload': 'http://localhost:3000',
      '/formalize': 'http://localhost:3000',
      '/review': 'http://localhost:3000',
      '/reviews': 'http://localhost:3000',
      '/files': 'http://localhost:3000',
      '/download': 'http://localhost:3000',
      '/health': 'http://localhost:3000',
    },
  },
})
