import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 7475,
    proxy: {
      '/api': {
        target: 'http://localhost:7474',
        configure: (proxy, _options) => {
          proxy.on('proxyRes', (proxyRes, req, res) => {
            if (proxyRes.headers['content-type']?.includes('text/event-stream')) {
              res.setHeader('Cache-Control', 'no-cache')
              res.setHeader('Connection', 'keep-alive')
              // Disable buffering for SSE
              res.flushHeaders()
            }
          })
        }
      }
    }
  }
})
