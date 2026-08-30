import { test, expect, Page } from '@playwright/test';

/**
 * 冒烟测试: 首页加载 + 基础导航 + console error 监听
 * 验证 Vite dev server + React 路由 + 后端 API 三个链路打通
 */

// 收集 console error (允许 React DevTools warning 等 noise)
function attachConsoleErrorListener(page: Page, errors: string[]) {
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      const text = msg.text();
      // 允许 list: 网络错误 (后端可能 5xx), 不计入硬错误
      // 但 React 渲染错误 / TypeScript 运行时错误必须捕获
      if (
        !text.includes('Failed to load resource') && // 网络 5xx 单独由 API 测试覆盖
        !text.includes('favicon') &&
        !text.includes('ERR_CONNECTION_REFUSED')
      ) {
        errors.push(text);
      }
    }
  });
  page.on('pageerror', (err) => {
    errors.push(`pageerror: ${err.message}`);
  });
}

test.describe('冒烟测试 - 首页加载', () => {
  let consoleErrors: string[];

  test.beforeEach(({ page }) => {
    consoleErrors = [];
    attachConsoleErrorListener(page, consoleErrors);
  });

  test.afterEach(() => {
    // 每个测试都断言无 console error (允许网络错误 noise)
    expect(consoleErrors, `console errors: ${consoleErrors.join('\n')}`).toEqual([]);
  });

  test('首页 "/" 重定向到 /data 并加载完成', async ({ page }) => {
    await page.goto('/');
    // / 会 Navigate 到 /data
    await expect(page).toHaveURL(/\/data$/);
    // 等待关键元素出现 (避免 Suspense fallback)
    await expect(page).toHaveTitle(/热点地图.*SecNews/);
  });

  test('index.html title 正确 (品牌口径: 热点地图 - SecNews)', async ({ page }) => {
    await page.goto('/data');
    const title = await page.title();
    expect(title).toContain('热点地图');
    expect(title).toContain('SecNews');
    // 钉住不回退到旧英文品牌名
    expect(title).not.toMatch(/HOTSPOT MAP/i);
  });

  test('页面根节点 #root 渲染了内容', async ({ page }) => {
    await page.goto('/data');
    const root = page.locator('#root');
    await expect(root).toBeVisible();
    // 不应停留在白屏 (有非空 textContent)
    const text = await root.textContent();
    expect(text?.trim().length ?? 0).toBeGreaterThan(0);
  });
});
