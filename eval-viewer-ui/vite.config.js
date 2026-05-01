import { defineConfig } from 'vite'

export default defineConfig({
  resolve: {
    preserveSymlinks: true,
  },
  server: {
    fs: {
      allow: ['../..'],
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8002',
        changeOrigin: true,
      },
    },
  },
})
