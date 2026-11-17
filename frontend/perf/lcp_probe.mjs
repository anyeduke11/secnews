/**
 * LCP 基线探针 — 缺口 G1 (FRONTEND_REWRITE_V1_PLAN §7.1)
 *
 * 口径: 生产构建 (dist) + vite preview, 桌面视口 1440×900, Chromium 冷缓存,
 *       同一 API 夹具 (先 capture 抓一次真实响应, 再 measure 固定回放), 3 次取中位数。
 *
 * 用法:
 *   npm run build                                # 产物 dist
 *   npx vite preview --host 127.0.0.1 &          # 默认 4173
 *   node perf/lcp_probe.mjs capture              # 抓 /api/** 响应 → perf/lcp-api-fixture.json
 *   node perf/lcp_probe.mjs measure --runs=3     # 回放夹具 + 采 LCP
 *
 * 只用于性能口径留档; B6 复测须用同一脚本 + 同一夹具文件。
 */
import { chromium } from '@playwright/test';
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const FIXTURE = join(HERE, 'lcp-api-fixture.json');
const BASE = process.env.PROBE_BASE || 'http://127.0.0.1:4173';
const VIEWPORT = { width: 1440, height: 900 };
const SETTLE_MS = 5000; // load 后静置, 让数据落地并让 LCP 候选稳定

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

async function capture() {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: VIEWPORT });
  const page = await ctx.newPage();
  const saved = new Map();
  page.on('response', async res => {
    const req = res.request();
    const url = req.url();
    if (!url.includes('/api/')) return;
    const key = `${req.method()} ${url}`;
    if (saved.has(key)) return;
    const ct = res.headers()['content-type'] || '';
    if (ct.includes('text/event-stream')) {
      saved.set(key, { sse: true });
      return;
    }
    try {
      const body = await res.text();
      saved.set(key, { status: res.status(), ct, body });
    } catch {
      /* 响应体读取失败与 LCP 无关, 跳过 */
    }
  });
  await page.goto(BASE + '/', { waitUntil: 'load' });
  await page.waitForTimeout(SETTLE_MS);
  const entries = [...saved.entries()].map(([key, v]) => ({ key, ...v }));
  writeFileSync(FIXTURE, JSON.stringify({ base: BASE, captured_at: new Date().toISOString(), entries }, null, 0));
  await browser.close();
  const api = entries.filter(e => !e.sse);
  console.log(`[capture] ${entries.length} endpoints (${api.length} json + ${entries.length - api.length} sse) → ${FIXTURE}`);
  console.log(`[capture] bytes = ${readFileSync(FIXTURE).length}`);
}

async function measure(runs) {
  if (!existsSync(FIXTURE)) throw new Error(`缺少夹具 ${FIXTURE}, 先跑 capture`);
  const fixture = JSON.parse(readFileSync(FIXTURE, 'utf-8'));
  const map = new Map(fixture.entries.map(e => [e.key, e]));
  const browser = await chromium.launch();
  const results = [];
  for (let i = 0; i < runs; i++) {
    const ctx = await browser.newContext({ viewport: VIEWPORT }); // 每次新 context = 冷缓存
    const page = await ctx.newPage();
    await page.addInitScript(INIT);
    await page.route('**/api/**', async route => {
      const req = route.request();
      const hit = map.get(`${req.method()} ${req.url()}`);
      if (hit?.sse) {
        return route.fulfill({ status: 200, contentType: 'text/event-stream', body: 'retry: 60000\n\n' });
      }
      if (hit) {
        return route.fulfill({ status: hit.status, contentType: hit.ct || 'application/json', body: hit.body });
      }
      return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"probe-fixture-miss"}' });
    });
    await page.goto(BASE + '/', { waitUntil: 'load' });
    await page.waitForTimeout(SETTLE_MS);
    const r = await page.evaluate(() => ({ lcp: window.__lcp, el: window.__lcpEl }));
    results.push({ run: i + 1, lcp_ms: Math.round(r.lcp), element: r.el });
    await ctx.close();
  }
  await browser.close();
  const sorted = results.map(r => r.lcp_ms).sort((a, b) => a - b);
  const median = sorted[Math.floor(sorted.length / 2)];
  console.log(JSON.stringify({ base: BASE, viewport: VIEWPORT, fixture: fixture.captured_at, runs: results, median_ms: median }, null, 2));
}

const mode = process.argv[2];
const runsArg = process.argv.find(a => a.startsWith('--runs='));
const runs = Number(runsArg?.split('=')[1] || 3);
if (mode === 'capture') await capture();
else if (mode === 'measure') await measure(runs);
else throw new Error('用法: node perf/lcp_probe.mjs capture|measure [--runs=3]');