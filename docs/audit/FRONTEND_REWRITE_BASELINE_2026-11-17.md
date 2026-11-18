# 前端重构 V1 · B0 基线实测（2026-11-17）

> 依据：[`FRONTEND_REWRITE_V1_PLAN.md`](../FRONTEND_REWRITE_V1_PLAN.md) §6 B0 / §7.1 / §7.2。
> 本文件是**唯一基线存档**；后续批次只能与这里的数字比较，不得改用口头估计。
> 采集环境：macOS / Node（本机）/ `frontend/` 目录，v0.8.9 工作树，命令见各节。

## 1. 单元测试覆盖率基线

采集方式（新增 `@vitest/coverage-v8@2.x` 并在 `vite.config.ts` 增加 `test.coverage`，不设 thresholds）：

```bash
cd frontend && npx vitest run --coverage
# 汇总源: frontend/coverage/coverage-summary.json
```

| 指标 | 基线值 |
|---|---|
| Lines | **57.05%** |
| Statements | **57.05%** |
| Functions | **57.42%** |
| Branches | **76.39%** |

- 全量用例 **全部通过**（`vitest run` 退出码 0）。
- 统计范围：`src/**/*.{ts,tsx}`，排除 `*.test.*` / `src/test/**` / `*.d.ts`。
- **B1 起**按逐域下限 = 上述全局值回填 `coverage.thresholds`；只允许升，不允许降。

## 2. 首屏加载基线（桌面 1440×900 口径）

采集方式：

```bash
cd frontend && npx vite build --logLevel error
# 对 dist/assets/*.js 逐个 zlib.gzipSync 统计
```

### 2.1 首屏 `/` 路由 JS（gzip 字节）

> **两套口径定义**（2026-11-18 DEV-0396 固化；此前各批只用前者，且采集工具不一）：
>
> | 口径 | 定义 | 用途 |
> |---|---|---|
> | **A. 首屏 JS（3 chunk）** | `index-*.js` + `vendor-react-*.js` + `SentinelHomePage-*.js` 三者 gzip 之和 | 与本基线逐批可比；**批次退出条件「包体积不增」的判定口径** |
> | **B. 首屏 eager 闭包** | 以 `dist/index.html` 的 `<script>` / `<link modulepreload>` 为种子，递归**静态** `from"..."` import 闭包（含路由 chunk），排除仅被 `__vite__mapDeps` / `import()` 引用的懒加载 chunk | 浏览器首屏真实下载量（含共享 chunk） |
>
> 采集工具统一 **Node `zlib.gzipSync`（level 6）**。⚠️ `gzip -c` CLI 结果**不可比** —— 它把文件名写进头部，实测每 chunk 多约 147 B。
>
> 采样对象 = `frontend/dist`（`npm run build` 产物）。口径 B 的判定注意点：路由 chunk 若只被 `__vite__mapDeps` + `import()` 引用则**不属于**首屏（反之会虚高）。

口径 A（本节数字即此口径）：

| 组成 | gzip |
|---|---|
| `index-*.js`（应用入口 + 路由壳） | 27,119 |
| `vendor-react-*.js` | 53,816 |
| `SentinelHomePage-*.js` | 12,063 |
| **首屏 JS 合计** | **92,998** |

### 2.2 首屏 CSS（gzip 字节）

| 组成 | gzip |
|---|---|
| `index-*.css`（全局 token + 壳样式） | 15,146 |
| `pages-*.css`（工具页共享） | 1,361 |

### 2.3 全量 JS 产物

- 全量 JS gzip = **549,589 B** / 69 个 chunk。
- 最大三项：`vendor-echarts` 213,486 / `vendor-react` 53,816 / `SettingsPage` 35,723。
- 与 `docs/audit/V089_M4_BUNDLE_FIX_2026-11-17.md` 的 577,813 B 差异属**统计口径不同**（后者含 CSS 与 HTML），本文件以本命令输出为准。

### 2.4 LCP 基线 —— **未采集（显式缺口）**

契约 §7.1 要求「首屏路由 JS gzip ≤ 基线 80% **且** LCP ≤ 基线 80%，取 min」。
本次 **只完成 JS gzip 侧**；LCP 需要 `vite preview` + Playwright 在 1440×900 冷缓存下取 3 次中位数，本批次未执行。

- 状态：**❌ 未测**，不得在 B6 验收报告里用任何估算值替代。
- 补齐方式（B4 首个重写页面落地前必须完成）：`npx vite preview` → Playwright 固定夹具路由 `/` → `PerformanceObserver` 取 `largest-contentful-paint` → 3 次中位数，结果回填本节。
- 在 LCP 基线缺失期间，B6 的「性能提升 ≥20%」只能以 JS gzip 单指标判定，并须在验收报告中显式声明该降级。

## 3. 待补项汇总

| 项 | 状态 |
|---|---|
| 覆盖率 4 指标 | ✅ 已入档 |
| 首屏 JS gzip | ✅ 已入档 |
| 首屏 CSS gzip | ✅ 已入档 |
| 全量 JS gzip | ✅ 已入档 |
| LCP（桌面 1440×900 冷缓存） | ❌ 未测，见 §2.4 |
| PRD 92 条能力 → 路由/组件/测试四向映射 | ⏳ 未产出（B4 前必须完成） |