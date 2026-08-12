import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// En dev local  : http://127.0.0.1:8000
// En Docker     : ARIA_API_URL=http://api:8000  injecté par docker-compose
const FASTAPI = process.env['ARIA_API_URL'] ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    // Polling requis : les événements inotify ne traversent pas les volumes
    // montés Windows → Docker Desktop, donc chokidar ne voit jamais les writes.
    watch: {
      usePolling: true,
      interval: 300,
    },
    // Dev only — proxied vers FastAPI. Ignoré dans `npm run build`.
    proxy: {
      '/auth':        FASTAPI,
      '/upload':      FASTAPI,
      '/jobs':        FASTAPI,
      '/registry':    FASTAPI,
      '/llm':         FASTAPI,
      '/rag':         FASTAPI,
      '/users':       FASTAPI,
      '/approvals':   FASTAPI,
      '/reports':     FASTAPI,
      '^/automation/': FASTAPI,
      '/bulk':        FASTAPI,
      '/openapi':     FASTAPI,
      '/audit-logs':  FASTAPI,
      '/maintenance': FASTAPI,
    },
  },
  build: {
    // En prod, tout est servi depuis FastAPI sur le même origin → pas de CORS, pas de proxy
    outDir: 'dist',
  },
  root: path.resolve(__dirname, '.'),
})
