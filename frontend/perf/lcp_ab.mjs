/**
 * lcp_ab.mjs — LCP A/B 对照: 外部字体是否主导 LCP
 *
 * 用法: node perf/lcp_ab.mjs [--runs=3]
 * 口径与 lcp_probe.mjs 一致 (同一夹具 / 同视口 / 每轮冷缓存), 只额外
 * 增加一组「拦截字体 CDN」的对照, 用于分离「网络抖动」与「代码回归」。
 */
import { chromium } from '@playwright/test';
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const FIXTURE = join(HERE, 'lcp-api-fixture.json');
const BASE = process.env.PROBE_BASE || 'http://127.0.0.1:4173';
const VIEWPORT = { width: 1440, height: 900 };
const SETTLE_MS = 5000;

const INIT = () => {
  window.__lcp = 0;
  window.__lcpEl = '';
  new PerformanceObserver(list => {
    for (const e of list.getEntries()) {
      window.__lcp = e.startTime;
      const el = e.element;
      window.__lcpEl = el ? `${el.tagName.toLowerCase()}.${(el.className || '').toString().slice(0, 80)}` : (e.url || '');
    }
  }).observe({ type: 'largest-contentful-paint', buffered: true });
};

const fixture = JSON.parse(readFileSync(FIXTURE, 'utf-8'));
const map = new Map(fixture.entries.map(e => [e.key, e]));

async function run(browser, blockFonts) {
  const ctx = await browser.newContext({ viewport: VIEWPORT });
  const page = await ctx.newPage();
  await page.addInitScript(INIT);
  if (blockFonts) {
    await page.route('**://fonts.googleapis.com/**', r => r.abort());
    await page.route('**://fonts.gstatic.com/**', r => r.abort());
  }
  await page.route('**/api/**', async route => {
    const req = route.request();
    const hit = map.get(`${req.method()} ${req.url()}`);
    if (hit?.sse) return route.fulfill({ status: 200, contentType: 'text/event-stream', body: 'retry: 60000\n\n' });
    if (hit) return route.fulfill({ status: hit.status, contentType: hit.ct || 'application/json', body: hit.body });
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"probe-fixture-miss"}' });
  });
  // 口径与 lcp_probe.mjs 一致 (waitUntil: 'load'), 但容错: 外部字体 CDN
  // 偶发把 load 拖过 15s → goto 抛超时后**继续**读已发生的 LCP,
  // 而不是整轮报废 (LCP 元素渲染早于 load 完成)。
  try {
    await page.goto(BASE + '/', { waitUntil: 'load', timeout: 15000 });
  } catch {
    /* load 未在 15s 内完成 —— 记为超时但继续采样 */
  }
  await page.waitForTimeout(SETTLE_MS);
  const r = await page.evaluate(() => ({ lcp: window.__lcp, el: window.__lcpEl }));
  await ctx.close();
  return { lcp_ms: Math.round(r.lcp), element: r.el };
}

const runs = Number(process.argv.find(a => a.startsWith('--runs='))?.split('=')[1] || 3);
const browser = await chromium.launch();
const out = {};
for (const [label, block] of [['with_fonts', false], ['no_fonts', true]]) {
  const rs = [];
  for (let i = 0; i < runs; i++) rs.push(await run(browser, block));
  const sorted = rs.map(r => r.lcp_ms).sort((a, b) => a - b);
  out[label] = { runs: rs, median_ms: sorted[Math.floor(sorted.length / 2)] };
  console.log(`[${label}] ${JSON.stringify(rs.map(r => r.lcp_ms))} median=${out[label].median_ms} el=${rs[0].element}`);
}
await browser.close();
console.log('\n' + JSON.stringify(out, null, 2));
