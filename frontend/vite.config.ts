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
    //
    // Plusieurs de ces préfixes (/users, /bulk, /governance, /connections, …)
    // sont AUSSI des routes React Router côté frontend — un rechargement dur
    // (F5) sur /governance envoie une vraie navigation de page avec
    // `Accept: text/html`, que le proxy interceptait et renvoyait vers
    // FastAPI (qui n'a pas de route HTML à cette adresse → page blanche /
    // 404). `bypass` laisse Vite servir index.html pour toute navigation de
    // page, et ne proxie vers FastAPI que les vrais appels API (fetch/XHR,
    // qui n'envoient pas `Accept: text/html` en tête de liste).
    proxy: (() => {
      const bypass = (req: { headers: Record<string, string | string[] | undefined> }) => {
        const accept = req.headers.accept
        if (typeof accept === 'string' && accept.split(',')[0]?.trim() === 'text/html') {
          return '/index.html'
        }
      }
      const targets = [
        '/auth', '/upload', '/jobs', '/registry', '/llm', '/rag', '/users',
        '/teams', '/approvals', '/notifications', '/reports', '^/automation/',
        '/bulk', '/openapi', '/audit-logs', '/maintenance', '/governance', '/connections',
      ]
      return Object.fromEntries(targets.map(t => [t, { target: FASTAPI, bypass }]))
    })(),
  },
  build: {
    // En prod, tout est servi depuis FastAPI sur le même origin → pas de CORS, pas de proxy
    outDir: 'dist',
  },
  root: path.resolve(__dirname, '.'),
})
