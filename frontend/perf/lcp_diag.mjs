/**
 * lcp_diag.mjs — 诊断: load 事件超时是否由外部字体 stylesheet 阻塞
 *
 * 用法: node perf/lcp_diag.mjs
 * 输出: 三种情形下 goto('load') 是否在 30s 内完成
 *   A  原样 (不拦字体)
 *   B  拦截 fonts.googleapis.com / fonts.gstatic.com (模拟离线/慢网)
 *   C  拦截 + 记录 load 事件时刻
 */
import { chromium } from '@playwright/test';

const BASE = process.env.PROBE_BASE || 'http://127.0.0.1:4173';

async function probe(browser, label, blockFonts) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const pending = [];
  page.on('request', (r) => {
    if (r.url().includes('fonts.g')) pending.push(r.url());
  });
  if (blockFonts) {
    await page.route('**://fonts.googleapis.com/**', (r) => r.abort());
    await page.route('**://fonts.gstatic.com/**', (r) => r.abort());
  }
  const t0 = Date.now();
  let result;
  try {
    await page.goto(BASE + '/', { waitUntil: 'load', timeout: 15000 });
    result = `load OK in ${Date.now() - t0} ms`;
  } catch (e) {
    result = `load TIMEOUT after ${Date.now() - t0} ms`;
  }
  console.log(`[${label}] ${result} | 字体请求数=${pending.length} ${pending.slice(0, 2).join(' ')}`);
  await ctx.close();
  return result;
}

const browser = await chromium.launch();
await probe(browser, 'A 不拦字体', false);
await probe(browser, 'B 拦字体  ', true);
await browser.close();
