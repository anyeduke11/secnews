# 前端视觉系统盘点（design/_research/frontend-visual.md）

> 盘点日期：2026-11-17。范围：`frontend/`（React 18 + Vite + Tailwind）壳层、主题 token、组件规模、设计契约现状。
> 方法：全部结论以仓库一手代码（文件路径 + 行号）为证据，未采信 `.mimosa/` hook-state 下的历史基线快照；文档与代码冲突处单列，不代为和解。

---

## 1. SentinelShell 壳结构

**文件**：`frontend/src/components/sentinel/SentinelShell.tsx`（约 457 行），样式 `frontend/src/components/sentinel/sentinel.css`。

- **定位**：全站唯一壳（根 `AGENTS.md:40` v0.8.5 壳纪律：「SentinelShell 4-tab + 管道心跳条常驻」）。工具页经 `PageLayout` 也包在本壳内（`layer={null}`）。
- **壳三段**（`SentinelShell.tsx:7-10` 头注释，DEV-0181 编辑部形态）：
  1. **masthead 报头**：品牌（衬线 `mh-title` SecNews + 等宽 `mh-sub` SECURITY INTEL STATION）+ 四菜单排版式导航 + `CommandBar`（v0.8.6 P1-4 常驻）+ 主题三态切换按钮 + 时钟。样式 `sentinel.css:95-160`。
  2. **bandnav 版面条**：当前菜单二级域 chip，sticky 吸顶；`BANDNAV_DEFS` 定义见 `SentinelShell.tsx:152`，chip 按 feature gate 过滤渲染；收起态持久化 localStorage `bandnav-collapsed`（DEV-0188，`SentinelShell.tsx:162-183`）。
  3. **pressbar 印务条**：即**管道心跳条**。
- **4-tab 实现**：`LAYER_DEFS`（`SentinelShell.tsx:141-146`）声明四菜单 → 路由：`data→/`（资讯）、`knowledge→/knowledge`、`action→/action`、`settings→/settings`。类型 `SentinelLayer = 'data' | 'judge' | 'action' | 'knowledge' | 'settings'`（`SentinelShell.tsx:31`；`judge` 为三层时代遗留成员，`menuOf` 已不返回，`SentinelShell.tsx:153`）。渲染为 `mh-nav` 内 `.nv` 链接（衬线主字 + accent 下划线 active 态，`sentinel.css:113-131`），非图标式 tab。
- **管道心跳条组件名与位置**：**没有独立组件文件**。它是 `SentinelShell` 渲染函数内的 `<section className="pressbar" aria-label="采集管道状态">`（`SentinelShell.tsx:367-436`），样式在 `sentinel.css:171-213`（「印务条 pressbar (管道心跳)」区块）。组成：
  - 五个 `pipe-block`：管道状态（健康三态着色 mint/amber/red）、源在线 `active/total`（stale/dev 差值 delta）、今日收录、管线漏斗（`/api/kl/pipeline/stats` 生命周期漏斗）、队列三态（pending/running/error）。
  - `pipe-live` 右侧：`.pulse` 呼吸点（`sn-pulse` 动画 2.4s 无限循环，`sentinel.css:193-197`；`prefers-reduced-motion` 时关闭）+ `PIPELINE LIVE` 标签 + `.beat-lights` 采集源灯条（**16 灯**，DEV-0194 由 40 灯缩减，`SentinelShell.tsx:411-424`；正常 mint / 重试 amber / 离线 red）。
- **数据链**：`fetchPipe()`（`SentinelShell.tsx:89`，合并 `/api/sources/health` 与 `/api/kl/pipeline/stats`）→ `PipeContext` → `usePipe()`（`SentinelShell.tsx:129`）供子页免重复拉取；SSE 到达时 `usePipeReloadOnSse()`（`SentinelShell.tsx:441`）10s 节流刷新（DEV-0167，`mountedReload` 优先于 context）。
- **守卫测试**：`frontend/src/components/sentinel/SentinelShell.test.tsx`、`frontend/src/routes/__tests__/nav4_shell.test.tsx`。

## 2. PageLayout 与 menuOf() 归属逻辑

**文件**：`frontend/src/components/PageLayout.tsx`。

- `PageLayout()`（`PageLayout.tsx:9-26`）= `ToastProvider` + skip-link + `<SentinelShell layer={null}>` + `#main-content.tool-main`（居中容器 `max-w-[1580px]`）。头注释（`PageLayout.tsx:2-8`）记录两次壳统一：2026-09-10 删左侧 AppNav；2026-09-13 NAV4 后工具页高亮由 `menuOf` 接管（`SentinelMoreMenu`/`UTILITY_GROUPS` 已物理删除）。
- 同文件 `SentinelLayout()`（`PageLayout.tsx:29-39`）：三层全屏路由组，仅 ToastProvider + Outlet，壳由各页内嵌 SentinelShell 提供。
- **`menuOf(pathname)`**：`SentinelShell.tsx:215-234`。优先精确匹配（`/`、`/judge*`、`/cases*`→data），再前缀匹配 `/knowledge|/deep|/reviews|/reader`→knowledge、`/action`→action、`/settings|/secrets|/sync|/skills|/codegarden|/maint`→settings；工具页按语义归属（`/report`→action，`/tags|/extract|/search|/dashboard|/skill-store`→knowledge，`/quality|/history`→data）；`/secnews` 子视图按内容归属（feed/pipeline/analytics→data，knowledge→knowledge，analyze→action，observability→settings，默认 data）；未命中（如 `/oauth-callback`）返回 `null` 兜底。
- 消费点：`const activeLayer = layer ?? menuOf(pathname)`（`SentinelShell.tsx:262`）——显式 layer 优先，工具页自动推断。
- 归属覆盖守卫：`nav4_shell.test.tsx:54`（「menuOf() 必须覆盖 27 条路由归属（无 null 悬空）」）等 32 用例。

## 3. 主题系统（三态 light / dark / paper）

### 3.1 状态与切换

- **状态机**：`frontend/src/contexts/ThemeContext.tsx`。`ThemeMode = 'dark' | 'light' | 'paper'`（`ThemeContext.tsx:9`），`THEME_CYCLE = ['light','dark','paper']`（`:11`），`cycleTheme()` 三态轮换；`getInitialTheme()` 默认 **light**，持久化 localStorage `hotspot-theme`；写入 `document.documentElement` 的 `data-theme` 属性（`:24-29`）；监听设置页 `theme-changed` 事件消除双轨（`:32-45`）。

### 3.2 Token 定义位置

| 层 | 文件 | 内容 |
| --- | --- | --- |
| 全局唯一真相源 | `frontend/src/index.css` | `:root` 亮色默认块（`:158` 起，Stage1 light-first）；`:root[data-theme="dark"]`（`:63` 起）；`:root[data-theme="paper"]`（`:249` 起）；编辑部 alias 层 `:root`（`:333` 起，`--paper/--card/--ok/--ff-*` 等纯转发，禁止重声明既有 token）；`.pgx-*` 工具类映射（`:360` 起，渐进迁移桥梁） |
| Tailwind 映射 | `frontend/tailwind.config.js` | `colors`（cat-* / accent / dark-* / text-*）、`borderRadius`、`spacing`、`boxShadow`、`zIndex`、`transitionDuration/Timing` **全部转发 CSS 变量**，不写字面值；`darkMode: ['class','[data-theme="dark"]']`（预留 variant）；覆盖 `fontSize`（xs 11.5px / sm 13px / base 15px / lg 17px / xl 20px）与 `fontFamily`（sans=Inter 栈 / mono=JetBrains Mono 栈） |
| 壳 scoped 转发 | `frontend/src/components/sentinel/sentinel.css:26-40` | `--sn-*` 别名层（`--sn-bg:var(--bg-primary)` 等），约定「不在 scoped 层重复字面值」 |
| 断点 token | `frontend/src/styles/breakpoints.css` | `--bp-sm 640 / --bp-md 820 / --bp-lg 1080 / --bp-xl 1240 / --bp-2xl 1440`（v1.0.1 收敛 9 处散落断点；`index.css:8` 经 `@import` 引入） |

### 3.3 三态核心色板（实际值，index.css）

| token | light（默认） | dark | paper |
| --- | --- | --- | --- |
| `--bg-primary` | `#edf1f7` 冷白纸底 | `#0a1628` 近黑深蓝 | `#F7F4EE` 暖米黄纸 |
| `--bg-card` | `#ffffff` | `#0f2140` | `#fdf8ec` |
| `--bg-hover` | `#e2e9f3` | `#13294d` | `#f5f0e6` |
| `--ink` / `--text-primary` | `#14294a` 深海军蓝墨 | `#eef3fa` | `#1C1917` 深褐墨（AA 11.7:1，`index.css:266` 注释） |
| `--ink-2` / `--text-secondary` | `#45597c` | `#9db0c9` | `#5a4a36` |
| `--ink-3` / `--text-muted` | `#7188a8` | `#5f7492` | `#8a7659` |
| `--accent` | `#04785c` | `#00e5a0` | `#BE3426`（编辑红） |
| `--mint`（正常/新增/激活） | `#04785c` | `#00e5a0` | `#2E6B4F` |
| `--amber`（需注意） | `#a86314` | `#ffab5e` | `#A0691F` |
| `--red`（仅漏洞告警） | `#cc3d50` | `#ff6470` | `#BE3426` |
| `--color-info` | `#0e7490` | `#4dd6e2` | `#3B5B78` |
| `--line` / `--border-color` | `rgba(22,43,80,0.13)` | `rgba(148,180,220,0.14)` | `#E4DED2` 实色细线 |

语义三色锁纪律（三态通用）：mint=正常/新增/激活，amber=需注意，red 专属漏洞告警（`index.css` 各主题块注释；`sentinel.css:9`）。分类色（`--color-ai/security/finance/startup/bid/general/github/tech`，暗/亮同色相不同明度）与图表 severity 七档（`--chart-severity-critical…none`）各主题独立定义（`index.css:110-133` 暗 / `:212-235` 亮 / paper 块内沿用编辑部版）。

### 3.4 字体 / 圆角 / 间距 / 其他（`:root` 公共段，`index.css:10-58`）

- **字体栈**：`--font-mono: 'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, 'Fira Code', 'Cascadia Code', monospace`（`:11`）；`--font-sans: 'Inter', system-ui, … 'PingFang SC', 'Noto Sans SC', sans-serif`（`:12`）；`--font-serif: 'Source Han Serif SC', 'Noto Serif SC', 'Songti SC', Georgia, 'Times New Roman', serif`（`:15`，P2 纸面版衬线，paper 块内重申 `:308-309`）。
- **基础排版**：`body = mono 13px / 1.65`（`index.css:397-406`；移动/平板/≥2xl 升 14px，`:409-427`）；`.sentinel` 壳 = **sans 15px / 1.6**（`sentinel.css:41-48`）；工具页内容 `.sentinel .tool-main` 复位回 body 口径 mono 13/1.65（`sentinel.css:66-68`）。等宽数字：`.num` 用 `font-feature-settings:'tnum'`（`sentinel.css:72`）。
- **圆角**：`--radius-sm 6px / md 8px / lg 10px / xl 10px / full 9999px`（`index.css:17-21`，「圆角统一三档 6/8/10」）。
- **间距**：`--space-0..8 = 0/4/8/12/16/20/24/32/40px`（`index.css:23-31`，4px 网格）。
- **z 层级**：base 0 / dropdown 100 / sticky 200 / overlay 300 / modal 400 / popover 500 / toast 600 / tooltip 700（`index.css:33-41`）。
- **动效**：`--duration-fast 120ms / normal 200ms / slow 320ms`，`--ease-out cubic-bezier(0.16,1,0.3,1)`（`index.css:44-48`）；动效强度 MOTION_INTENSITY: 3（`:466` 区块头）。
- **零霓虹纪律**：三态均 `--shadow-card/-elevated/-glow: none`，层次只靠 hairline 与 1-3% 亮度差（`index.css:127-133` 暗 / `:226-232` 亮 / `:312-318` paper）；可读性下限 `--text-min: 11px`（`:57`）。

### 3.5 文档与代码冲突（记录，不和解）

1. **paper 覆写范围**：`index.css:249-252` 与 `ThemeContext.tsx:5-6` 均称 paper「仅覆写 bg/ink/font 6 个核心 token，mint/amber/red 沿用亮色值不动」；但 paper 块内实际覆写了 mint/amber/red/accent、分类色、line、阴影等全链约 60 项（`index.css:273-282, 292-300, 303`）。以块内实际值为准。
2. 根 `AGENTS.md` / 任务上下文称 paper「最小侵入仅覆写 6 核心 token」，同上以代码为准。

## 4. components/ 目录按域分组清单

路径 `frontend/src/components/`。统计口径：非测试 `.ts/.tsx` 文件数（`*.test.*` 单列）。合计 **21 个子域 178 个非测试文件 + 顶层 37 个散件 ≈ 215 个组件文件**，子域测试 70 个 + 顶层测试 12 个。

| 域目录 | 非测试 | 测试 | 代表组件 |
| --- | --- | --- | --- |
| `settings/` | 30 | 18 | SettingsPage、FeatureGatesCard、SourceSettings、ModelPoolPanel、quality/ 五面板 |
| `secnews/` | 27 | 6 | feed/FeedView、pipeline/FunnelBar、pipeline/SourceMatrixCard、observability/ObservabilityDashboard、analytics/SecNewsAnalytics、CveHeatmap |
| `codegarden/` | 23 | 4 | ProjectBoard、ServiceTopology、dependency-graph/DepGraph、resource-hub/PortPool、service-mesh/ |
| `sentinel/` | 17 | 12 | **SentinelShell**、SentinelHomePage、SentinelActionPage、SentinelGraphPage、CommandBar、SentinelRail、action/ 五 Stage 组件 |
| `knowledge/` | 16 | 10 | KnowledgeTabs、KnowledgeHubPage、KnowledgeLibraryPage、KnowledgeImport/Process/Compile、AttentionHeatmap |
| `secrets/` | 10 | 2 | SecretsPage、UnlockModal、RotationBanner、StatusBar |
| `sync/` | 10 | 0 | SyncStatusPanel、SyncConfigForm、SyncHistory、SyncHeader |
| `v1/` | 9 | 5 | V1Prototype、CaseDetail、panels/SignalPanel、panels/CaseQueuePanel、panels/ExecOverviewPanel |
| `report/` | 7 | 0 | ReportPage、DailyReport、WeeklyReport、MonthlyReport |
| `skills/` | 7 | 3 | SkillStore、SkillBuilder、SkillDetail、RunHistory |
| `shared/` | 6 | 3 | EChart、editorial/InfiniteCanvas、editorial/StatCard、editorial/Stamp、ReviewCard、NoteEditor |
| `security/` | 4 | 0 | SecurityGraph、ComplianceMatrix、SecurityEntityDetail |
| `layout/` | 3 | 0 | LayerTable、LayerCard、OnboardingHint |
| `action/` | 2 | 2 | ApprovalInbox、CopilotCards |
| `dashboard/` `events/` `extract/` `quality/` `reader/` `search/` `tags/` | 各 1 | 1/1/0/1/1/1/0 | 各域单组件 |
| **顶层散件** | 37 | 12 | PageLayout、Toast、ErrorBoundary、Icon、HotspotCard、KnowledgeGraph、SkillsPage、MaintPage、DeepReadPage、ReviewPage 等 |

## 5. design/UI_UX_CONTRACT.md 要点摘要

**文件**：`design/UI_UX_CONTRACT.md`（2026-09-07，v1.0.0 重构收尾契约，风格基线 industrial-brutalist-ui）。

- **效力状态（读前必知）**：文件头 2026-09-08 标注「**部分废止 (SUPERSEDED)**」——壳层/导航条款（四入口 `/workbench /intel /cases /knowledge`、V1SentinelShell、移除管道状态条）不再作为实施依据，由 `docs/v0.8.5/V0.8.5_PLAN.md` 取代（v0.8 SentinelShell 唯一壳 + 管道心跳条全站常驻）；**视觉 token、状态语义、组件密度条款继续有效**。
- **仍有效的要点**（§3.2/3.3/6）：
  - 定位：安全数据密集终端，首屏回答「今天需要我判断/补/批准/验收什么」。
  - 字体纪律：数字一律 `tabular-nums`，状态色必须带文字 label 不只靠颜色；图标 lucide-react 锁版本、禁 emoji。
  - 密度：表格行 44-48px / 工具栏 40-44px / 输入框 32-36px；1px solid var(--line) 分层，不靠阴影；间距 4/8/12/16/24/32（4px 网格）；圆角控件 4px / 卡片 6px。
  - 组件模式：StatusBadge 五 kind（yellow 需处理 / red 失败风险 / green 已确认 / blue 进行中 / gray 等待）；DataTable 终端风（粘性表头、数字右对齐）；空状态 4 态（loading/empty/stale/error）；Toast dedupe_key 2s 合并 + localStorage 静音集。
  - 实施纪律 10 条：复用既有 CSS token 不另写一套、真实截图不装饰图、对比度 4.5:1、动效 120-200ms + 尊重 `prefers-reduced-motion`、写新组件前先 grep 既有等。
- **与现行实现冲突（勿直接采信契约）**：
  1. 契约 §3.2 主色（黄 `#d4a017` / 红 `#c1272d` / 绿 `#1f7a3a` / 蓝 `#2563eb`）与中性色（bg `#fafaf7`/`#161616`、线 `#d4d4d0`）在现行 `index.css` 哨兵色板中**均未出现**——现行是 mint/amber/red 语义三色锁 + 各主题色板。
  2. 契约 §3.1/3.3 的 AppNav（顶部 56px + 左侧 240px 侧栏）已随 2026-09-10 壳统一物理废除（`PageLayout.tsx:2-3` 注释：「左侧 AppNav 侧栏删除——其 14 项入口与壳内四菜单导航全量重复」）。
  3. 契约字号阶梯（正文 14 / 辅助 12 / 页标题 22）与 Tailwind 现行 `fontSize` 覆盖（base 15 / sm 13 / xs 11.5）不一致；以 tailwind.config.js + index.css 现行值为准。

## 6. 视觉相关 CSS 文件地图

| 文件 | 职责（取自文件头注释） |
| --- | --- |
| `frontend/src/index.css` | 全局 token 真相源 + base + 通用组件类（Typography/Animations/Layout/Cards/Forms/Buttons/Badge/EmptyState 等约 30 区块，`:383-1048`） |
| `frontend/src/styles/breakpoints.css` | 全局断点 token（5 档） |
| `frontend/src/components/sentinel/sentinel.css` | 哨兵终端壳 + 首页设计系统（`.sentinel` scoped，`--sn-*` 转发层） |
| `frontend/src/components/sentinel/sentinel-action.css` | 行动层「今日行动」屏（`ac-*` 前缀，V2 原型移植） |
| `frontend/src/components/sentinel/sentinel-graph.css` | 判断层知识图谱屏（禁止色板字面值；全站唯一脉冲动画归壳心跳条，`:8`） |
| `frontend/src/components/settings/settings-shell.css` | `/settings` v2 设计系统（`st-*` 命名族表单控件） |
| `frontend/src/components/shared/editorial/canvas.css` | InfiniteCanvas 无限画布（DEV-0184，令牌随主题翻转） |
| `frontend/src/components/shared/editorial/pages.css` | 编辑部页面族：`/knowledge/khub` 前厅、`/knowledge/library` 编目室、`/action/events` 通稿审核、`/reader/:id` 清样、`/quality` 校对室（DEV-0183） |

## 7. 待证项与边界

- `index.css` 其余 652 行（`:425-1048` Typography→Feed rows 等区块）仅登记区块名，未逐行核对值。
- 顶层散件 37 个中部分（如 `SoulViewer.tsx`、`FederationStatus.tsx`）未逐一确认消费路由，仅列名。
- 契约 §4（R24 收尾清单）的 ⏳/✅ 状态未核销——该清单描述 v1.0 弯路时期任务，与 v0.8+ 现状无关，未逐项验证。
