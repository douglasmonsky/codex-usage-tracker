import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  base: '/codex-usage-tracker-assets/react/',
  plugins: [react()],
  optimizeDeps: {
    exclude: ['echarts'],
  },
  build: {
    outDir: '../../src/codex_usage_tracker/plugin_data/dashboard/react',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        assetFileNames: 'assets/[name][extname]',
        chunkFileNames: 'assets/[name].js',
        entryFileNames: 'assets/dashboard-react.js',
        manualChunks(id) {
          if (id.includes('/src/app/zh-Hans/')) return 'locale-zh-Hans';
          return undefined;
        }
      }
    }
  },
  server: {
    port: 5173,
    strictPort: false
  }
});
