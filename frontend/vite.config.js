import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 默认只构建本地 dist；发布时显式传 --outDir，避免测试构建覆盖正在服务的产物。
export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    host: true, // 手机同局域网可访问 dev server（HMR 调试用）
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8787', changeOrigin: true },
      '/media': { target: 'http://127.0.0.1:8787', changeOrigin: true },
    },
  },
})
