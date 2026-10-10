import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // `npm run dev` alatt az /api kéréseket a helyben futó backend kapja
    // (élesben ugyanezt az nginx végzi, lásd nginx.conf).
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
