/**
 * visual_regress.mjs — 视觉回归机检 (前端重构 V1 · B9-c, 2026-11-19)
 *
 * 对指定路由逐页截图 + 导出页头区域 outerHTML, 供两次构建之间做逐字节/逐 DOM 比对。
 * 仓库此前无视觉基线, 本工具把「人工走查」前置为可机械比对的证据。
 *
 * 用法:
 *   npx vite preview --host 127.0.0.1 --port 4173 --strictPort   # 先起 preview
 *   node perf/visual_regress.mjs http://127.0.0.1:4173 /tmp/vis-b9 /tags /search
 *
 * 产出:
 *   <outDir>/<route>.png            整页截图 (fullPage)
 *   <outDir>/<route>.header.html    页头区域 outerHTML (h1 的最近 header/div 祖先)
 *
 * 注: 后端不在时所有 API 一律回放 '{}', 页面走空态/错误态 —— 页头仍渲染, 即改动面。
 */
import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const baseUrl = process.argv[2];
const outDir = process.argv[3];
const routes = process.argv.slice(4);

if (!baseUrl || !outDir || routes.length === 0) {
  console.error('usage: node perf/visual_regress.mjs <baseUrl> <outDir> <route...>');
  process.exit(2);
}
mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch();
const results = [];

for (const route of routes) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  await page.route('**/*', (r) => {
    const u = r.request().url();
    if (u.startsWith(baseUrl)) return r.continue();
    return r.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
  let status = 'ok';
  try {
    // SSE 常驻连接会让 networkidle 永不达成, 故用 domcontentloaded + 固定静默期
    await page.goto(baseUrl + route, { waitUntil: 'domcontentloaded', timeout: 15000 });
  } catch (e) {
    status = 'nav-warn: ' + String(e.message).slice(0, 60);
  }
  await page.waitForTimeout(1200);
  // 屏蔽非确定性元素 (壳层时钟 / 呼吸动画), 否则同一构建两次截图即不一致 → 像素比对不可用
  await page.addStyleTag({
    content: `.clock, .pulse { visibility: hidden !important; }
              *, *::before, *::after { animation: none !important; transition: none !important; }`,
  });
  await page.waitForTimeout(200);
  const name = route.replace(/[^a-z0-9]+/gi, '_') || 'root';
  await page.screenshot({ path: join(outDir, `${name}.png`), fullPage: true });
  const html = await page.evaluate(() => {
    const h1 = document.querySelector('h1');
    if (!h1) return '(no h1)';
    const root = h1.closest('header, div');
    return root ? root.outerHTML : h1.outerHTML;
  });
  writeFileSync(join(outDir, `${name}.header.html`), html);
  results.push({ route, status, header_len: html.length });
  await ctx.close();
}
await browser.close();

console.log(JSON.stringify(results, null, 2));
