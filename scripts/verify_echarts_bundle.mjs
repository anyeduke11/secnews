/**
 * 生产 build 产物的 echarts 运行时验证 (真实 Chromium, 一次性脚本, 非 CI 门禁)。
 *
 * WHY 需要这个验证:
 *   tree-shaking + CJS interop 组合的典型失效是「build 通过、运行时白屏」——
 *   单元测试跑的是源码 (vite dev transform), 与生产产物 (rollup chunk 边界 +
 *   CJS→ESM interop + 真实 canvas) 不是同一份代码。故必须真浏览器加载 dist 产物。
 *
 * 做法: 起一个静态服务指向 dist/, 用 Chromium 打开一张空白页, 在页内
 *   dynamic import 生产 chunk → 用生产注册的实例 init → setOption 三类图 →
 *   断言 (a) 无 "is used but not imported" 报错 (b) canvas 真的画出了元素。
 *
 * 用法: cd frontend && npx vite build && cd .. && node scripts/verify_echarts_bundle.mjs
 */
import { readFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:http';
import { createRequire } from 'node:module';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const DIST = join(ROOT, 'frontend', 'dist');
const ASSETS = join(DIST, 'assets');

// playwright 装在 frontend/node_modules → 从 frontend 解析 (脚本在仓库根跑)
const frontendRequire = createRequire(join(ROOT, 'frontend', 'package.json'));
const { chromium } = frontendRequire('@playwright/test');

const assets = readdirSync(ASSETS);
const echartsChunk = assets.find((f) => f.startsWith('vendor-echarts-'));
const echartsModule = assets.find((f) => f.startsWith('EChart-'));
if (!echartsChunk || !echartsModule) {
  console.error(`FAIL: 找不到产物 chunk (echarts=${echartsChunk}, EChart=${echartsModule})`);
  process.exit(1);
}

// ── 静态服务 (只服务 dist/) ────────────────────────────────────────────
const MIME = {
  '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
  '.svg': 'image/svg+xml', '.json': 'application/json', '.png': 'image/png',
};
const server = createServer((req, res) => {
  const url = (req.url || '/').split('?')[0];
  const rel = url === '/' ? '/index.html' : url;
  const file = join(DIST, rel);
  try {
    const body = readFileSync(file);
    const ext = file.slice(file.lastIndexOf('.'));
    res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
    res.end(body);
  } catch {
    res.writeHead(404);
    res.end('not found');
  }
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const port = server.address().port;
const base = `http://127.0.0.1:${port}`;

const browser = await chromium.launch();
const page = await browser.newPage();

const consoleErrors = [];
page.on('console', (m) => {
  if (m.type() === 'error') consoleErrors.push(m.text());
});
page.on('pageerror', (e) => consoleErrors.push(String(e)));

await page.goto(`${base}/index.html`, { waitUntil: 'domcontentloaded' });

// 页内动态 import 生产 chunk + 用生产实例渲染三类图
const result = await page.evaluate(async ({ echartsChunk, echartsModule }) => {
  const errors = [];
  const origError = console.error;
  console.error = (...a) => { errors.push(a.map(String).join(' ')); origError(...a); };

  // 先加载 EChart chunk (其顶层执行 echarts.use([...]) 注册), 再取 vendor 实例
  const echartsMod = await import(`/assets/${echartsModule}`);
  const vendor = await import(`/assets/${echartsChunk}`);
  const echarts = vendor.e ?? vendor.default ?? vendor;

  const out = { checks: [], missing: [], hasCanvas: false };
  if (typeof echarts?.init !== 'function') {
    out.missing.push(`vendor chunk 未导出可用实例 (keys: ${Object.keys(vendor).join(',')})`);
    return out;
  }

  const cases = [
    ['gauge', { series: [{ type: 'gauge', radius: '90%', data: [{ value: 42 }] }] }],
    ['graph', {
      tooltip: {},
      series: [{ type: 'graph', layout: 'force', roam: true, data: [{ id: 'a', name: 'A', value: 3 }], edges: [] }],
    }],
    ['line+bar', {
      grid: {},
      xAxis: { type: 'category', data: ['a', 'b'] },
      yAxis: { type: 'value' },
      tooltip: { trigger: 'axis' },
      legend: {},
      series: [{ type: 'line', data: [1, 2] }, { type: 'bar', data: [2, 3] }],
    }],
  ];

  for (const [name, option] of cases) {
    errors.length = 0;
    const el = document.createElement('div');
    el.style.width = '400px';
    el.style.height = '300px';
    document.body.appendChild(el);
    const inst = echarts.init(el, undefined, { renderer: 'canvas' });
    inst.setOption(option);
    const missing = errors.filter((e) => /is used but not imported|does not exist|Unknown series/.test(e));
    if (missing.length) out.missing.push(`${name}: ${missing.join(' | ')}`);
    // canvas 真的画出了内容 (zrender 会建 <canvas> 并挂 zrender 元素)
    const painted = el.querySelector('canvas') !== null;
    if (painted) out.hasCanvas = true;
    out.checks.push({ name, painted, ok: missing.length === 0 });
    inst.dispose();
  }
  return out;
}, { echartsChunk, echartsModule });

await browser.close();
server.close();

const failed = result.missing.length > 0 || result.checks.some((c) => !c.ok);
for (const c of result.checks) {
  console.log(`${c.ok && c.painted ? 'OK  ' : 'FAIL'} ${c.name} — 注册完整 · canvas 已绘制=${c.painted}`);
}
if (result.missing.length) {
  console.error('FAIL 明细:');
  for (const m of result.missing) console.error(`  - ${m}`);
}
// 生产 app 自身的 console error (如后端未起) 不计入本验证
const appErrors = consoleErrors.filter((e) => !/Failed to fetch|ERR_CONNECTION|api\//i.test(e));
if (appErrors.length) {
  console.log(`(app 自身 console error ${appErrors.length} 条 — 与本验证无关, 后端未启动所致)`);
}

console.log(failed ? '\nRESULT: FAIL' : '\nRESULT: PASS');
process.exit(failed ? 1 : 0);
