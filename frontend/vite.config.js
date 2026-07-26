import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig({
  plugins: [
    vue(),
    AutoImport({
      resolvers: [ElementPlusResolver()],
    }),
    Components({
      resolvers: [ElementPlusResolver()],
    }),
  ],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('/@antv/')) return 'vendor-g6'
          if (id.includes('/element-plus/') || id.includes('/@element-plus/')) {
            return 'vendor-element-plus'
          }
          if (/\/(mammoth|marked|dompurify|jszip|pdfjs-dist)\//.test(id)) {
            return 'vendor-document-preview'
          }
          if (/\/(vue|vue-router|@vue)\//.test(id)) return 'vendor-vue'
          return undefined
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})

