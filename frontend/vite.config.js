import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 构建产物直接进 <项目根>/deploy/dist（仓库之外），由 FastAPI 托管。
// 注意路径层级：本文件在 <repo>/frontend/，outDir 相对「工程根」解析，
// 所以要 ../../deploy/dist —— 写成 ../deploy 会落到 <repo>/deploy（错误）。
export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: '../../deploy/dist',
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
