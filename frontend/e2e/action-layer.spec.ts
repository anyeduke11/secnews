import { test, expect, Page } from '@playwright/test';

/**
 * 行动层 (/action) e2e 测试
 * - /action/report
 * - /action/todos
 * - /action/review
 *
 * 路由参考: frontend/src/routes/index.tsx
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

const PAGES = [
  { path: '/action', name: '行动层入口' },
  { path: '/action/report', name: 'Report 报告' },
  { path: '/action/todos', name: 'Todos 待办' },
  { path: '/action/review', name: 'Review 复盘' },
] as const;

test.describe('行动层 /action', () => {
  let consoleErrors: string[];

  test.beforeEach(({ page }) => {
    consoleErrors = [];
    attachErrorListener(page, consoleErrors);
  });

  test.afterEach(() => {
    expect(consoleErrors, `console errors: ${consoleErrors.join('\n')}`).toEqual([]);
  });

  for (const p of PAGES) {
    test(`${p.name} (${p.path}) 加载无错误`, async ({ page }) => {
      await page.goto(p.path);
      // 期望停留在 action 域 (而非被 fallback 路由到 /data)
      await expect(page).toHaveURL(/\/action/);
      await expect(page.getByText('正在排版…')).toHaveCount(0, { timeout: 15_000 });
      // 等待 lazy fetch
      await page.waitForTimeout(1500);
      const root = page.locator('#root');
      const text = await root.textContent();
      expect(text?.trim().length ?? 0).toBeGreaterThan(0);
    });
  }
});
