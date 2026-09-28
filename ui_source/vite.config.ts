import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/static/',
  build: {
    outDir: '../static',
    emptyOutDir: true,
    // recharts is ~500KB and only the Overview donut needs it, so it is loaded
    // through React.lazy rather than bundled into the entry chunk. Rollup
    // splits it out automatically from that dynamic import — no manualChunks
    // needed, and an explicit one would defeat the lazy boundary.
    chunkSizeWarningLimit: 600,
  },
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000' },
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
})
