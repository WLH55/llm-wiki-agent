import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 容器内通过服务名访问 backend；本机开发回落到 localhost
const backendTarget = process.env.VITE_BACKEND_URL || 'http://localhost:8008'

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
