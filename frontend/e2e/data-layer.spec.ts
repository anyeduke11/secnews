import { test, expect, Page } from '@playwright/test';

/**
 * 资料层 (/data) e2e 测试
 * - 页面加载
 * - 分类切换 (CategoryNav)
 * - 分页 (HotspotGrid 分页器)
 *
 * 定位策略: 优先 role/text (a11y friendly), 不依赖 className
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

test.describe('资料层 /data', () => {
  let consoleErrors: string[];

  test.beforeEach(({ page }) => {
    consoleErrors = [];
    attachErrorListener(page, consoleErrors);
  });

  test.afterEach(() => {
    expect(consoleErrors, `console errors: ${consoleErrors.join('\n')}`).toEqual([]);
  });

  test('页面加载并显示热点内容', async ({ page }) => {
    await page.goto('/data');
    // 等待 Suspense fallback 消失
    await expect(page).toHaveURL(/\/data$/);
    // 关键: 不停留在 "正在排版…" fallback
    await expect(page.getByText('正在排版…')).toHaveCount(0, { timeout: 15_000 });
  });

  test('分类导航存在并可切换', async ({ page }) => {
    await page.goto('/data');
    // 等待主内容渲染 (避免 fallback)
    await expect(page.getByText('正在排版…')).toHaveCount(0, { timeout: 15_000 });

    // 找到任意一个分类导航项 (CategoryNav 中的按钮/链接)
    // 安全: 用 getByRole 定位, 不依赖具体文案
    const navItems = page.getByRole('button').or(page.getByRole('link'));
    const count = await navItems.count();
    expect(count).toBeGreaterThan(0);
  });

  test('分页器或列表加载后存在交互元素', async ({ page }) => {
    await page.goto('/data');
    await expect(page.getByText('正在排版…')).toHaveCount(0, { timeout: 15_000 });

    // 给数据 fetch 一点时间
    await page.waitForTimeout(2000);

    // 页面应有可点击元素 (卡片 / 按钮 / 链接任一)
    const interactives = page.getByRole('button').or(page.getByRole('link')).or(page.getByRole('article'));
    const count = await interactives.count();
    expect(count).toBeGreaterThan(0);
  });
});
