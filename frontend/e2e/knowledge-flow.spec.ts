import { test, expect, Page } from '@playwright/test';

/**
 * 知识流 (/knowledge) 6 模式切换 e2e 测试
 * 模式: briefing / scan / deep-read / alert / outbox / review
 * (deep-read/:id 需要具体 id, 跳过该子路由)
 *
 * 路由参考: frontend/src/routes/index.tsx
 * - /knowledge → redirect → /knowledge/import
 * - /knowledge/briefing
 * - /knowledge/scan
 * - /knowledge/deep-read → redirect → /knowledge/scan
 * - /knowledge/alert
 * - /knowledge/outbox
 * - /knowledge/review
 */

function attachErrorListener(page: Page, errors: string[]) {
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      const text = msg.text();
      if (
        !text.includes('Failed to load resource') &&
        !text.includes('favicon') &&
        !text.includes('ERR_CONNECTION_REFUSED')
      ) {
        errors.push(text);
      }
    }
  });
  page.on('pageerror', (err) => errors.push(`pageerror: ${err.message}`));
}

const MODES = [
  { path: '/knowledge/briefing', name: 'Briefing 简报' },
  { path: '/knowledge/scan', name: 'Scan 扫描' },
  { path: '/knowledge/alert', name: 'Alert 告警' },
  { path: '/knowledge/outbox', name: 'Outbox 整理' },
  { path: '/knowledge/review', name: 'Review 复习' },
] as const;

test.describe('知识流 /knowledge 6 模式切换', () => {
  let consoleErrors: string[];

  test.beforeEach(({ page }) => {
    consoleErrors = [];
    attachErrorListener(page, consoleErrors);
  });

  test.afterEach(() => {
    expect(consoleErrors, `console errors: ${consoleErrors.join('\n')}`).toEqual([]);
  });

  test('/knowledge 默认重定向到 import', async ({ page }) => {
    await page.goto('/knowledge');
    await expect(page).toHaveURL(/\/knowledge\/import/);
  });

  for (const mode of MODES) {
    test(`${mode.name} (${mode.path}) 加载无 console error`, async ({ page }) => {
      await page.goto(mode.path);
      // Suspense fallback 应消失
      await expect(page.getByText('正在排版…')).toHaveCount(0, { timeout: 15_000 });
      // URL 应保持 (未被 redirect 到 /data 的 404 fallback)
      await expect(page).toHaveURL(new RegExp(mode.path.replace('/', '\\/')));
      // 页面有内容
      const root = page.locator('#root');
      const text = await root.textContent();
      expect(text?.trim().length ?? 0).toBeGreaterThan(0);
    });
  }
});
