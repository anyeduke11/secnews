import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { configDefaults } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 8898,
    // Phase 50: 禁止端口漂移 — 8898 被占用直接报错, 不自动切到 5173/5174
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      }
    }
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    // e2e/*.spec.ts 是 Playwright 用例 (有自己的 runner), vitest 收集会在
    // import 阶段报 "test.describe() called here" 假失败
    exclude: [...configDefaults.exclude, 'e2e/**'],
  },
  // v0.5 M1-Task3: manualChunks 拆 vendor
  // 验收: 主 chunk <300KB (基线 1.14MB)
  // - vendor-react: react + react-dom + react-router-dom (~140KB)
  // - vendor-echarts: echarts + echarts-for-react (~700KB)
  // - vendor-misc: 其他第三方
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-react': ['react', 'react-dom', 'react-router-dom'],
          'vendor-echarts': ['echarts', 'echarts-for-react'],
        },
      },
    },
  },
})
