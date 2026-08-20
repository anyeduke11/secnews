import { test, expect, Page } from '@playwright/test';

/**
 * 判断层 (/judge) e2e 测试
 * - /judge/trends — 趋势分析
 * - /judge/bid-analysis — 标讯分析
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

test.describe('判断层 /judge', () => {
  let consoleErrors: string[];

  test.beforeEach(({ page }) => {
    consoleErrors = [];
    attachErrorListener(page, consoleErrors);
  });

  test.afterEach(() => {
    expect(consoleErrors, `console errors: ${consoleErrors.join('\n')}`).toEqual([]);
  });

  test('/judge 入口加载', async ({ page }) => {
    await page.goto('/judge');
    await expect(page).toHaveURL(/\/judge/);
    await expect(page.getByText('正在排版…')).toHaveCount(0, { timeout: 15_000 });
  });

  test('/judge/trends 趋势页加载', async ({ page }) => {
    await page.goto('/judge/trends');
    await expect(page).toHaveURL(/\/judge\/trends/);
    await expect(page.getByText('正在排版…')).toHaveCount(0, { timeout: 15_000 });
    // 等待数据 fetch
    await page.waitForTimeout(2000);
    const root = page.locator('#root');
    const text = await root.textContent();
    expect(text?.trim().length ?? 0).toBeGreaterThan(0);
  });

  test('/judge/bid-analysis 标讯分析页加载', async ({ page }) => {
    await page.goto('/judge/bid-analysis');
    await expect(page).toHaveURL(/\/judge\/bid-analysis/);
    await expect(page.getByText('正在排版…')).toHaveCount(0, { timeout: 15_000 });
    await page.waitForTimeout(2000);
    const root = page.locator('#root');
    const text = await root.textContent();
    expect(text?.trim().length ?? 0).toBeGreaterThan(0);
  });
});
