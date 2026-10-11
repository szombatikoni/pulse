import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // `npm run dev` alatt az /api kéréseket a helyben futó backend kapja
    // (élesben ugyanezt az nginx végzi, lásd nginx.conf).
    proxy: {
      // 127.0.0.1, nem localhost: a Node a localhostot előbb IPv6-on próbálná.
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
