import { defineConfig, devices } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';

// ESM 中 __dirname 不存在 (package.json "type": "module")
const __dirname = dirname(fileURLToPath(import.meta.url));

/**
 * Playwright E2E 配置 (hotspot 单人本地工作站)
 * - 仅测 chromium (单人项目, 无需跨浏览器)
 * - baseURL: 前端 dev server http://localhost:8898
 * - webServer: 自动启动 `npm run dev`
 * - 后端 (FastAPI 8000) 需预先运行 (单人 SQLite, 不自动启动避免锁)
 *
 * 超时设置 30s (dev server 首次启动慢, lazy-loaded 路由首帧需时间)
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false, // 单人本地 SQLite, 串行避免前端 cache 竞态
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1, // 单 worker (与 dev server 共享 Vite 缓存)
  reporter: process.env.CI ? [['github'], ['list']] : 'list',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: 'http://localhost:8898',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    // 捕获 console error (测试用例可监听 page.on('console'))
    console: true,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:8898',
    timeout: 60_000,
    reuseExistingServer: true, // 复用已在 8898 运行的 dev server (本机 dev 环境)
    cwd: __dirname, // frontend/
  },
});
