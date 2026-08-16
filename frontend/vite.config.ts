import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 容器内通过服务名访问 backend（VITE_BACKEND_URL 覆盖）；
// 本机开发用显式 IPv4 127.0.0.1，避免 localhost 解析到 IPv6 打到别的服务
// 本机后端跑 8008（见 Makefile dev-app / docker-compose.dev.yml 注释）
const backendTarget = process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8008'

// Vite 配置：React 插件 + 开发模式代理 /api → 后端
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: backendTarget,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
