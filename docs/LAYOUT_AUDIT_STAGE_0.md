# Hotspot 界面改造 Stage 0 Audit 报告

> 静态代码 audit 时间：2026-08-18
> 范围：frontend/src（207 个 .tsx / 35,792 行）
> 备份基线：`backup/stage-0-init-20260818-165119` @ `b9306a90`
> 配套计划文档：`docs/LAYOUT_REDESIGN_PLAN.md`

## TL;DR

全局发现 **6 类共 12 个问题**，按影响面排序：

| 优先级 | 类型 | 问题 | 影响面 |
|---|---|---|---|
| P0 | 代码债 | legacy alias 卡片/分隔符类未收编 | 全站 |
| P0 | 双轨矛盾 | CSS 暗色默认 vs JS 状态亮色默认 | 全站 |
| P0 | 路由债 | App.tsx 单文件 287 行集中 50+ lazy import | 全站 |
| P1 | 可读性 | 9px / 10px 极小字号共 6 处 | 局部组件 |
| P1 | 导航债 | 旧路由 / 新路由 / 三层架构 命名冲突 | 全站 |
| P2 | 适配债 | 移动端只有 1 个全局断点 | 全站 |

每子系统 Top 3 改造点见 [§3 子系统优先级](#3-子系统优先级)。

---

## 1. 全局性问题

### 1.1 P0 / Legacy alias 卡片类未收编 [L0 视觉层]

**位置**：`frontend/src/index.css:427-455`

**现状**：
- `card-base`（line 427）— 当前主用
- `editorial-card` + `tech-card`（line 439-449）— 注释标注 "Legacy aliases"
- `card-compact`（line 451）— 与 `card-base` 等价但无 hover

**问题**：
- 4 个类名指向同一组 token，新代码选哪个没标准
- `editorial-card.featured` 这种变体在新代码里用不到但仍占着 CSS 体积
- 检索时难分主次

**理由先收编**：
- 减少 CSS 体积（实测可省约 30 行）
- 消除 "新组件应该用哪个" 的认知负担
- 视觉回归测试只需测一个目标类

**建议改造**：
- 收编到 `card-base` 一个类
- `editorial-card.featured` → 用 `card-base` + inline style 表达"featured"
- 不动 hover 行为（保持现状）
- 全文件 grep 看哪几个组件还在用 editorial-card / tech-card / card-compact，逐个替换

**风险等级**：L0（纯 CSS 收编，不动 JSX）
**预计影响文件**：5-15 个（需要 grep 后确认）

---

### 1.2 P0 / 双轨矛盾：CSS 暗色默认 vs JS 状态亮色默认 [L0 视觉层]

**位置**：
- CSS：`frontend/src/index.css:46` `[data-theme="dark"], :root:not([data-theme])` 应用暗色 token
- JS：`frontend/src/App.tsx:180` `getInitialTheme()` 默认返回 `'light'`

**现状**：
- 用户首次打开：JS 设 `data-theme=light`，CSS 走 `[data-theme="light"]` 分支（line 98）
- 但 CSS `:root:not([data-theme])` 选择器是兜底（如果 JS 跑慢了 / hydrate 之前）
- CLAUDE.md 写"v1.9 Editorial: 日报版 (light) 为新默认"

**问题**：
- 暗色 token 是工程默认值（与 CLAUDE.md 的 light 默认叙事不一致）
- 主题切换瞬间可能有 0.1s 闪色
- 测试时到底默认哪个，要靠 `localStorage.getItem('hotspot-theme')`

**理由先改**：
- 与产品叙事一致（CLAUDE.md 说 light 是新默认）
- 避免首屏闪色
- 减少 dark / light token 互换的边角 bug

**建议改造**（两种方案，先讨论）：

**方案 A**：CSS 默认改 light
- `:root` 直接走 light token
- 暗色用 `[data-theme="dark"]` 单独覆盖
- JS 默认保持 light
- 改动小，但损失"暗色优先"的工程习惯

**方案 B**：JS 默认改 dark
- `getInitialTheme()` 返回 `'dark'`
- 与 CSS 默认对齐
- 改动更小（只动 1 行）
- 但与 CLAUDE.md 写的 v1.9 light 默认叙事不符

**建议**：方案 B，先动 JS 一行 + 在 CLAUDE.md / docs/CHANGELOG 同步更新叙事。视觉叙事对齐工程实现。

**风险等级**：L0
**预计影响文件**：2-3 个

---

### 1.3 P0 / 路由债：App.tsx 单文件 287 行集中 50+ lazy import [L1 区块层]

**位置**：`frontend/src/App.tsx:1-291`

**现状**：
- 50+ `React.lazy()` 集中声明
- 50+ `<Route>` 散在同一文件
- 内嵌 `<ThemeContext>` + 3 个 useEffect（theme persistence + theme-changed 监听 + theme toggle）
- `CategoryRedirect` + `PageFallback` 等 helper 函数也在这里

**问题**：
- 改一个路由的 lazy chunk 路径要滚到 App.tsx 顶部
- 主题状态逻辑和路由耦合
- 旧路由重定向（line 232-234, 250-254）混在主路由里
- 任何对路由的改动都要打开这 287 行文件

**理由先拆**：
- 加快后续 Stage 1-6 的改动速度（不用每次都改 App.tsx）
- 让路由声明 = 应用结构图，懒加载位置 = 业务模块位置，1:1 映射
- ThemeContext 抽到独立文件，App.tsx 回到"组合 + 路由"两个职责

**建议改造**：
- 新建 `frontend/src/routes/index.tsx` 导出 routes 数组
- 新建 `frontend/src/routes/lazy-imports.ts` 集中所有 lazy()
- 拆 `frontend/src/contexts/ThemeContext.tsx`（从 App.tsx 抽）
- App.tsx 只剩 ThemeContext provider + `<Routes>` 调用
- 目标：App.tsx < 80 行

**风险等级**：L1（动结构但不动业务）
**预计影响文件**：3-5 个新建 + App.tsx 瘦身

---

### 1.4 P1 / 极小字号 6 处 [L0 视觉层]

**位置**（按严重度排序）：

| 位置 | 元素 | 当前字号 | 风险 |
|---|---|---|---|
| `index.css:371-374` | `.flow-action-desc` | `9px` | 极小，移动端几乎不可读 |
| `index.css:405-415` | `.view-more-link` | `10px` | 偏小，链接辨识度低 |
| `index.css:482-497` | `.cluster-badge` | `10px` | 偏小，标签辨识度低 |
| `index.css:592-619` | `.btn-ghost` / `.btn-primary` 等 | `11px` | 偏小，CTA 权重不足 |
| `index.css:562-568` | `.editorial-input` | `13px` | OK，但 placeholder 颜色 `var(--text-muted)` 对比度需 audit |
| `KnowledgeTabs.tsx` | MODE_ITEMS 标签 | 待 audit | 6 模式切换的标签可能不一致 |

**问题**：
- 9px 在桌面端勉强，移动端（dpr 缩放后）几乎不可读
- 10px 字号在 1366x768 / 1920x1080 屏幕 OK，但 4K 缩放后偏小
- 11px 按钮文字配 30px min-height，字号/容器比 = 0.37，密度高但 CTA 感弱

**理由先改**：
- 字号是 accessibility 的硬底线（WCAG 不强制字号但要求可读）
- 移动端适配先从字号入手最容易见效
- 一旦改了，后续 Stage 2-6 都有统一基线

**建议改造**：
- 9px flow-action-desc → 11px（描述类文字下限）
- 10px 徽章/链接 → 11px（保留粗体 + tracking 强化辨识）
- 11px 按钮 → 12px（CTA 权重提升）
- 全局最小字号声明：CSS `:root` 加 `--text-min: 11px`，所有用 `font-size: < 11px` 触发警告
- 移动端 `< 768px`：所有 size +1px 兜底（已部分实现，可强化）

**风险等级**：L0（纯 CSS）
**预计影响文件**：3-5 个（index.css 集中改 + 个别组件覆盖）

---

### 1.5 P1 / 导航债：旧路由 / 新路由 / 三层架构 命名冲突 [L2 动线层]

**位置**：
- App.tsx:218-286 路由声明
- App.tsx:232-234, 250-254 旧路由重定向

**现状**：
- 顶层三层架构路由：`/data`, `/judge`, `/action`
- 知识库：`/knowledge/*`（12 个子路由）
- CodeGarden：`/codegarden`, `/codegarden/phase2b`
- 旧路由重定向：
  - `/` → `/data`
  - `/category/:cat` → `/data?category=`
  - `/weekly-report` → `/report`
  - `/judge/quality` → `/quality/rejection`
  - `/judge/heatmap` → `/knowledge/heatmap`
  - `/judge/graph` → `/knowledge/process`
  - `/judge/compile` → `/knowledge/compile`
  - `/judge/read` → `/knowledge/briefing`
  - `/knowledge/deep-read` → `/knowledge/scan`

**问题**：
- `/judge/heatmap` 和 `/knowledge/heatmap` 是同一页面，但路径前缀暗示两种不同的入口
- `/knowledge/deep-read/:id` 是真路由，重定向到 `/knowledge/scan` 后用户 URL 不变（vs `/deep-read` redirect `to="scan"`，URL 变了）
- `brief` 路由（line 285）和 `/knowledge/briefing` 重复
- 三层架构色（data/judge/action）+ 7 分类色（ai/security/finance/...）+ 3 模式色（briefing/scan/...）之间没有视觉关联图

**理由先 audit 不一定先改**：
- 路由一旦改，SEO + 用户书签全受影响
- 应当分阶段：先 audit 实际使用频率，再决定哪些去重
- 但至少要把 `/judge/heatmap` vs `/knowledge/heatmap` 这类"视觉指向不一致"的路径收编

**建议改造**（分两批）：

**批 1（Stage 1 顺手做）**：
- 在所有旧路由重定向处加注释，标注"v0.4 兼容性保留"
- `/brief` vs `/knowledge/briefing`：留一个去一个
- `/deep` vs `/knowledge/deep-read`：留一个去一个

**批 2（Stage 6 跨子系统时做）**：
- 三层架构色 / 分类色 / 模式色做"色彩语义字典"
- 统一所有页面顶部 LayerHeader 的色彩信号

**风险等级**：L1-L2（动结构 + 行为）
**预计影响文件**：5-8 个

---

### 1.6 P2 / 适配债：移动端只有 1 个全局断点 [L0 视觉层]

**位置**：`frontend/src/index.css:163-165`

**现状**：
```css
@media (max-width: 767px) {
  body { font-size: 14px; }
}
```

只有 1 个断点 767px（即 < 768px 视作移动端）。其他全部按桌面端渲染。

**问题**：
- 平板（768-1024）按桌面渲染，但触摸优化缺失
- 1366-1920 桌面也走同一套样式，没有"宽屏"和"普通桌面"区分
- 列表/卡片栅格在 1920+ 屏幕上视觉太散
- Knowledge 6 模式的横向 tab 切换在移动端可能换行

**理由先改**：
- 适配是用户明确点名的诉求
- 单点断点最简单，先把第二档断点（平板 / 宽屏）补上
- 不需要重新设计各页面，只在关键组件加 `md:` / `lg:` 适配

**建议改造**：
- 全局 token 化断点：
  ```css
  --bp-sm: 640px;
  --bp-md: 768px;
  --bp-lg: 1024px;
  --bp-xl: 1280px;
  --bp-2xl: 1536px;
  ```
- 至少在 `Header` / `CategoryNav` / `HotspotGrid` 三个高频组件加 `md:` 适配
- Stage 6 时针对 Knowledge 6 模式切换做移动端专门优化（横向滚动 or 抽屉）

**风险等级**：L0-L1
**预计影响文件**：5-10 个

---

## 2. 状态判断

| 维度 | 现状 | 评估 |
|---|---|---|
| 设计 token 完整性 | 颜色 / 圆角 / 间距 / z-index / 缓动 / 持续时间 都有 token | ✅ 完整 |
| Token 一致性 | 多个 legacy alias 并存 | ⚠️ 待收编 |
| 动效体系 | 7 个 keyframe + reduced-motion 兜底 | ✅ 完整 |
| 字体系统 | mono 主 / sans / serif 三套 | ✅ 完整 |
| 主题双轨 | CSS 暗色默认 vs JS light 默认 | ❌ 矛盾 |
| 路由架构 | 3 层架构 + 12 知识库子路由 + 兼容层 | ⚠️ 集中度过高 |
| 适配层 | 单断点 767px | ❌ 不够 |
| 可读性 | 9-11px 字号占多数 | ⚠️ 偏紧 |

整体评分：token 体系 **70 分**（完整但有冗余），适配层 **40 分**（明显短板）。

---

## 3. 子系统优先级

### 3.1 SecNews 热点聚合（`/data` + 子路由）

**代表页面**：`DataLayerPage.tsx` (312 行)

**Top 3 改造点**：

1. **L1 列表/网格切换按钮过小** — `HotspotGrid` 切换控件在 Header 右侧，按钮 11px / 30px，桌面端不显眼。建议提升到 12px / 32px + 加上当前模式 icon。

2. **L1 筛选器与主内容视觉权重不均** — 左侧分类导航 (`CategoryNav`) + 顶部时间范围 (`timeRange`) + 关键词 (`keyword`) + 地区 (`region`) + 数据源 (`sourceFilter`) 共 5 个筛选器，挤在 Header 下方一排。建议分组：核心筛选（分类 + 时间）放主区，次要筛选（地区 + 数据源）放次级抽屉 / popover。

3. **L0 信息密度 token 不一致** — 卡片 padding 在 data 页面是 `p-4`（CLAUDE.md 说 DENSITY 8），但右侧 `LayerCard` / `PipelineFlow` 用 `gap-3.5` 14px，与左列不齐。统一到 token。

---

### 3.2 Knowledge 知识库（`/knowledge/*` 12 子路由）

**代表页面**：`OutboxMode.tsx` (659 行 最大), `KnowledgeTabs.tsx` (234 行), `BriefingMode.tsx` (417 行)

**Top 3 改造点**：

1. **L1 6 模式切换视觉权重不均** — `MODE_ITEMS` 数组 6 项，但每项的 `label` 长度不一（"快速扫描" 4 字 vs "深度阅读" 4 字 vs "简报" 2 字 vs "整理" 2 字 vs "复习" 2 字 vs "告警" 2 字），切换栏左侧稀右侧密。建议统一为 2-3 字 + 副标签（hover 显示完整）。

2. **L0 批量操作区与列表视觉冲突** — `OutboxMode` 选中条目后顶部出批量操作条（"标记已读 / 归档 / 生成摘要"），与"按 attention_score 降序"的列表头视觉权重接近，混在一起会看不清选中状态。建议批量操作条加 1px 顶部 border + 半透明 backdrop，与列表视觉分层。

3. **L1 4 大领域 → 6 模式 两级导航混乱** — 第一级是 `KnowledgeTabs`（4 领域 import/process/compile/compound），第二级是 `MODE_ITEMS`（6 模式 briefing/scan/...）。路由层 /knowledge/briefing 直接进 6 模式但跳过了 4 领域步骤。建议：默认进 /knowledge 自动落到 4 领域页，6 模式在 4 领域内作为子步骤，URL 路径同步（如 /knowledge/import/briefing）。

---

### 3.3 CodeGarden 项目管理（`/codegarden` + `phase2b`）

**代表页面**：`ProjectBoard.tsx` (65 行), `ServiceMesh.test.tsx` (178 行), `EventBus.tsx` (274 行), `ProjectDetail.tsx` (238 行), 3 个子目录（`dependency-graph`, `resource-hub`, `service-mesh`）

**Top 3 改造点**：

1. **L1 关系图节点信息密度低** — `ServiceTopology` / `DependencyGraph` 是 ECharts 渲染，节点标签挤在小盒子里，关系线无 hover 高亮。建议：节点加 attention hint（依赖强度色阶），hover 时高亮上下游关系线。

2. **L1 看板列宽自适应缺失** — `ProjectBoard` 只有 65 行（很薄），暗示可能是简单平铺。`ProjectDetail` 238 行承担详情重任。建议：列表/详情左右分栏（list 35% / detail 65%），加 `lg:` 断点，< lg 时详情上推。

3. **L0 子目录间视觉一致性弱** — 3 个子目录（dependency-graph / resource-hub / service-mesh）独立组件，但渲染风格未确认。建议：抽 `RelationshipGraphShell` 组件统一外壳（标题栏 + 工具栏 + 图区 + 详情侧栏），3 个子目录只负责内部数据渲染。

---

### 3.4 ActionLayer / JudgeLayer / Report（辅助页）

**Top 3 改造点**（简略）：

1. `ActionLayerPage` / `JudgeLayerPage` 与 `DataLayerPage` 三层架构视觉一致性 audit
2. `ReportPage` 日报/周报/月报的 3 模式切换视觉权重
3. `ActionReportPage` / `ActionCompoundPage` 等 7 个包装页与原页面的导航层级（看是否要 redirect 而不是包装）

---

### 3.5 Settings / Sync / Secrets / Skills / History / Todos（工具页）

**Top 3 改造点**（简略）：

1. Settings 内的分组（v0.4 主题切换、proxy、master key 等）信息密度 audit
2. SyncPage（CLAUDE.md 说 ~800 行）需要拆分
3. SecretsPage（同 ~800 行）需要拆分

---

## 4. Stage 1 启动建议

按 P0 → P1 → P2 顺序，Stage 1 建议聚焦**全局性**改造（问题 1.1-1.5），因为：

1. 这些是"全站性 token 债"，后续每个 Stage 都会受益
2. 风险等级都是 L0-L1（纯 CSS / 动结构不动业务逻辑）
3. 一次收编避免后续 Stage 2-6 反复撞同一面墙

**Stage 1 候选任务清单**（按 ROI 排序）：

| # | 任务 | 风险 | 估时 | 收益 |
|---|---|---|---|---|
| 1 | 收编 legacy 卡片类 (1.1) | L0 | 30 min | 全站 CSS 体积 -30 行 + 认知统一 |
| 2 | 修主题双轨 (1.2) | L0 | 15 min | 叙事对齐 + 消除闪色 |
| 3 | 拆 App.tsx 路由 (1.3) | L1 | 1-2 h | 后续改动速度 +50% |
| 4 | 字号下限提升 (1.4) | L0 | 30 min | 可读性 + 移动端基础 |
| 5 | 加断点 token (1.6) | L0 | 20 min | 适配层基础 |
| 6 | 路由命名整理 (1.5 批 1) | L1 | 30 min | 入口一致 |

**Stage 1 起点 backup**（未启动前）：
```bash
./scripts/layout-backup.sh stage-1-infra
```

**Stage 1 完结判定**：
- ✅ 卡片类只剩 `card-base` 一种
- ✅ 主题默认与叙事一致
- ✅ App.tsx < 80 行
- ✅ 全局无 < 11px 字号
- ✅ 5 个断点 token 就位

---

## 5. 风险与依赖

**Stage 1 依赖**：
- 用户确认 Stage 1 范围（上面 6 个任务都做？还是只做 Top 3？）
- 不需要后端配合
- 不需要测试改动（已有 vitest 286+ 用例覆盖核心，改造后跑一遍确认无 regression）

**Stage 2+ 依赖**：
- 截图或运行时访问（dev server 起来后我可以再 audit）
- 用户的痛点优先级（每个子系统 3 个改造点，用户可能想加 / 换）

**全局护栏**：
- 改造后跑 `cd frontend && npm run build` + `npm run test:run` 兜底
- 任何"为了好看"的主观改动都先列清单，让用户决定要不要做

---

**Stage 0 audit 完毕**。等待用户对 Stage 1 范围 + 优先级的确认。
