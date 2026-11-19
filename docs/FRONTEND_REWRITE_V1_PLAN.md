# Hotspot 前端重构 V1 · 契约文档

> **日期**: 2026-11-17
> **状态**: 已获 owner 裁决，进入 B0 执行
> **权威关系**: 本文是**实施契约**（怎么改、分批边界、验收口径）；产品能力与验收条件仍以 [`HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md`](HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md) 为准，路由/接口一致性仍以 [`v0.8.5/V0.8.5_PLAN.md`](v0.8.5/V0.8.5_PLAN.md) §5/§6/§10 为准。三者冲突时：PRD > V0.8.5_PLAN > 本文。
> **视觉条款取代关系**: 本文 §3 取代 `design/UI_UX_CONTRACT.md` 的视觉 token 与组件密度条款（该文件壳层条款已于 2026-09-08 superseded）。

---

## 0. 决策记录（owner 2026-11-17）

| # | 决策项 | 裁决 | 说明 |
|---|---|---|---|
| D1 | 重构范围 | **全量重写** | 用户明确选择"全量重写"，包含页面 JSX 与三份手写 CSS；契约层（类型/词条/路由语义/SSE/错误模型）按 §2.1 保留 |
| D2 | 性能口径 | **桌面端** | 暂不考虑移动端；首屏 ≥20% 的具体算法见 §7.1 |
| D3 | 视觉授权 | **允许完全重新设计** | 不受现有 Sentinel 视觉 token 约束；新视觉方向见 §3 |
| D4 | 迁移纪律 | **绞杀者模式（强制）** | 新架构与旧页面并存，路由逐域切换，**任何 commit 点仓库必须可构建、可部署、可回滚**。禁止"先删后建" |
| D5 | 壳数量 | **恒为 1** | 原地替换 `SentinelShell`，不新建并行壳（AGENTS.md 硬规则：禁止新一级入口/新壳） |
| R1 | CaseQueuePanel 未挂载（2026-11-18 裁决） | **补挂到 `/action`** | `CaseQueuePanel` 有组件有测试但从未挂入任何页面（`git log -S` 无挂载记录）；`ExecOverviewPanel` 只取 `open/in_progress`（limit 8）**不含 `blocked`**，二者非包含关系 → 判定为漏挂。B5 在 `/action` 挂入完整队列，并更正 ROUTE_REGISTRY «P1 已完成» 表述 |
| R2 | 20% 首屏目标口径（2026-11-18 裁决） | **口径暂不调整，增设 B5.5 瘦身批** | 口径 A 目标 74,398 B 中 `vendor-react` 已占 **53,816 B（72.3%）**，应用代码仅剩 20,582 B 预算而现状 38,942 B（需再砍 47%）→ JS 侧结构性不可达。裁定先跑 B5.5 专项瘦身并复测，再由数据决定是否降级口径；B6 才做最终判定 |
| R3 | §2.1 硬规则 3「≤300 行」与 §2.3「保留物」冲突（2026-11-18 裁决） | **按文件类别分层豁免，非全站豁免** | 事实基础：`types/index.ts` 907 行含 **569 行纯类型声明**、`types/codegarden.ts` 453 行含 338 行类型、`contexts/I18nContext.tsx` 957 行为词条表 —— 长度来自**声明式内容**而非逻辑密度，硬拆会把类型定义切碎、破坏 §2.3「契约层不重写」。裁定：① **契约层豁免**（`types/`、`api/`、`contexts/`、`lib/`、`hooks/realtime.ts`）—— 按文件职责拆分，**不按行数**；② **组件层不豁免**（页面/区块/视图组件一律 ≤300 行，含 `MaintPage` / `ItemDetailDialog` / `DeepReadPage` / `V1Prototype` / `HistoryPage` / `LayerCard` / `TodoItem` 等，均归 B6 拆）；③ 豁免清单进 §2.1 硬规则 3 的脚注，**不静默绕过**，逐条可查 |
| R4 | §7.1 首屏 ≥20% 双指标（2026-11-18 裁决，B5.5 后） | **降级为 LCP 单指标；JS 体积降为观测项** | 依据（实测，非估算）：口径 A 目标 74,398 B 中 `vendor-react` 独占 **53,816 B（72.3%）** = React 运行时不可压缩项；应用代码预算仅 20,582 B，B4 完成态实测 38,942 B（需再砍 47%）→ **JS 侧 20% 架构上结构性不可达**（与 R2 前置结论一致）。裁定：① **LCP ≤ 基线 80% 为唯一判定指标**（B5.5 实测 128 ms ≤ 201.6 ms **达标**）；② 首屏 JS 体积**降为观测项**，但每批必须登记且**不得高于基线**；③ 原 LCP 基线 252 ms 采于字体 CDN 恰好快响应的偶然条件，B6 复测须同脚本同夹具同网络条件，并记录带/不带字体两组以区分代码回归与网络抖动 |

> 编号约定：`D*` = 本表决策；`R*` = 2026-11-18 补充裁决。验证报告里的 `D1–D8` 是**契约偏差/偏差编号**，与本表 `D*` 不同序列。

---

## 1. 现状基线（实测 2026-11-17）

| 指标 | 数值 | 采集方式 |
|---|---|---|
| 非测试源码 | 267 文件 / 50,385 行 | `find frontend/src -name '*.ts*'` 排除 `*.test.*` |
| 测试 | 99 文件 / 15,375 行 | 同上，仅 `*.test.ts(x)` |
| 生产包 | 577,813 B gzip | `npm run build` 后 `dist/assets` 求和 |
| 手写 CSS | 1,070（`index.css`）+ 1,260（`sentinel/*.css`）= 2,330 行 | 行数统计 |
| 超 500 行文件 | 7 个 | `SentinelHomePage` 808 / `SentinelGraphPage` 762 / `CaseDetail` 784 / `SentinelActionPage` 573 / `ReviewOverlay` 573 / `SkillBuilder` 558 / `I18nContext` 957 |
| 组件域 | 20 个子域 + 约 40 个根目录散件 | 目录清点 |
| 数据调用 | 54 处组件直调 `getJSON`，仅 8 个域 API 模块 | grep |
| 三态渲染 | 54 处各自手写 loading/empty/error | grep |
| 原生 table | 17 套各自实现 | grep |

### 1.1 必须治好的五个结构病灶

| # | 病灶 | 证据 | 治标方案 |
|---|---|---|---|
| P1 | **God 组件** | `SentinelHomePage.tsx` 808 行 / 15 个 `useState`；`SentinelGraphPage.tsx` 762 行 / 13 个 | 拆为「容器（取数/状态编排）+ 区块（纯展示）」，单文件 ≤300 行 |
| P2 | **数据层碎片化** | 54 处直调 `getJSON`，无统一 key/缓存/失效 | §5 `useQuery` 工厂 + 域 API 模块收口 |
| P3 | **状态三态重复** | 54 处手写、17 套 table | §4 `AsyncState` + `DataTable` 原子 |
| P4 | **双套样式体系** | `index.css` 与 `sentinel.css` 各一套 token，`--sn-*` 二次别名 | §3 单一 token 源，`--sn-*` 仅迁移期别名 |
| P5 | **主题三轨同步** | CSS `data-theme` + `theme-changed` 事件 + localStorage | 单一 `ThemeProvider` 写 `<html data-theme>`，取消自定义事件 |

---

## 2. 目标架构

### 2.1 分层与依赖方向

```
L4  pages/        组装层：路由页面，唯一持有路由参数与跨区块状态
     ↓ 只允许向下
L3  domains/      业务域：useXxxQuery / useXxxMutation + 域组件
     ↓
L2  shell/        唯一壳：四菜单 + 管道心跳条 + 主题 + 全局 Toast
     ↓
L1  primitives/   无业务原子：StatusBadge / Panel / DataTable / AsyncState / PageHeader / Toolbar
     ↓
L0  tokens        纯 CSS 变量（三态主题），零 JS
```

**硬规则**
1. 依赖只能向下，禁止反向 import（`primitives` 不得 import `domains`）。
2. 跨域 import 必须经 `domains/<x>/index.ts` 公开出口，禁止深层路径。
3. 单个非测试文件 ≤300 行；超出即拆区块。
   - **契约层豁免（R3, 2026-11-18 裁决）**：`types/`、`api/`、`contexts/`、`lib/`、`hooks/realtime.ts` 下的文件**不适用**本条，改为**按文件职责拆分**（`api/` 一个域模块可含数十个端点函数；`types/` 是纯声明式契约）。豁免**仅限这些目录**，不适用于 `components/`、`pages/`、`hooks/`（`realtime.ts` 除外）、`primitives/`、`shell/` 任何文件。豁免清单逐条可查，不静默绕过。
   - **组件层零豁免**：页面 / 区块 / 视图 / 卡片组件一律 ≤300 行；超限即拆，不得以「历史遗留」「先挂着」为由留存。
4. `echarts` 只允许在 `primitives/EChart.tsx` 内 import（v0.8.9 M-4 成果，守卫测试保留）。
5. 禁止新增一级菜单或并行壳；新能力只能作为四菜单内的区块挂入。

### 2.2 目录规范

```
frontend/src/
├── tokens/            # L0: tokens.css（唯一 token 源）+ 三态主题
├── primitives/        # L1: 无业务原子（含 colocated test）
├── shell/             # L2: AppShell / MenuNav / PipeBar / ThemeProvider / ToastHost
├── domains/           # L3: 按菜单分域
│   ├── feed/          # 资讯（原 secnews + sentinel 首页区块）
│   ├── knowledge/     # 知识
│   ├── action/        # 行动
│   ├── settings/      # 设置
│   └── shared/        # 跨域复用（仅当 ≥2 域真实使用）
├── pages/             # L4: 路由页面（薄）
├── routes/            # 路由表（语义不变）+ lazy 表
├── hooks/             # 跨域 hook（useQuery 工厂、useSSE）
├── types/             # 契约类型（保留）
├── lib/               # fetch 封装、工具（保留）
└── contexts/          # I18n（保留）
```

### 2.3 保留物（不重写）

`api/v1.ts` 全部契约类型 · `types/index.ts` 领域类型与 CATEGORIES · `contexts/I18nContext.tsx` 词条 · `lib/api.ts` 错误契约 · `hooks/realtime.ts` SSE 事件名与 `collect_done` 契约 · `routes/index.tsx` 全部路由语义与重定向 · `EmptyState/Toast/ErrorBoundary/Icon` 四原子（移入 `primitives/` 后语义不变）· `generate_meta.py` 门禁相关无涉。

---

## 3. 视觉语言（重新设计）

**方向**: 安全运维终端 × 编辑器式工作台——高信息密度、等宽数字、细边框分区、零装饰。不做 Hero、不做嵌套大卡片、不做渐变营销风。

| 项 | 取值 |
|---|---|
| 字体 | 正文 `ui-sans-serif, -apple-system, "PingFang SC", "Microsoft YaHei"`；等宽/数字 `ui-monospace, "SF Mono", Menlo` + `font-variant-numeric: tabular-nums` |
| 字号阶 | 11 / 12 / 13 / 15 / 18 / 24 / 32 px（固定值，不用 vw） |
| 行高 | 正文 1.55；数据行 1.35 |
| 间距 | 4px 网格：4 / 8 / 12 / 16 / 24 / 32 / 48 |
| 栅格 | 桌面 12 列，内容区最大宽 1440px；断点 640 / 820 / 1080 / 1240 / 1440（沿用 `breakpoints.css` 变量） |
| 圆角 | 控件 3px / 容器 5px；不嵌套卡片 |
| 边框 | `1px solid var(--line)` 分区，不用阴影分层 |
| 状态色 | 需处理 amber / 风险 red / 已确认 green / 进行中 blue / 中性 gray，**全部带文字标签**，不靠颜色单独传义 |
| 密度 | 表格行 40px（原 44–48 收紧）/ 工具栏 40px / 输入 32px |
| 动效 | 120–180ms `ease-out` 过渡；尊重 `prefers-reduced-motion`；无滚动劫持 |
| 对比度 | 正文 ≥4.5:1，大字 ≥3:1 |
| 主题 | `light` / `dark` / `paper` 三态，全部经 `<html data-theme>` 驱动 |

**禁止清单**: emoji 图标 · 巨幅标题/欢迎区 · 卡片套卡片 · hover 改变布局尺寸 · 只靠颜色表达状态 · 深色模式用纯黑底（用 `#141414` 系）。

---

## 4. 组件原子（L1）

| 原子 | 职责 | 替换掉 |
|---|---|---|
| `StatusBadge` | 5 种语义状态，含文字 | 各页散落 badge |
| `Panel` | 带标题 / 操作区 / 空态插槽的容器 | 各页自拼卡片 |
| `DataTable` | 粘性表头、稳定列宽、数字右对齐、行 hover 仅变色 | 17 套原生 table |
| `AsyncState` | loading 骨架 / empty / error / stale 四态统一 | 54 处手写三态 |
| `PageHeader` | 标题 + 面包屑 + 主操作 + 元信息行 | 各页页头 |
| `Toolbar` | 筛选/搜索/视图切换的等距栏 | 各页工具条 |
| `SplitPane` | 主从两栏，可折叠辅助栏，窄屏降级为抽屉 | 手工 grid |
| `Inspector` | 右侧详情抽屉 | 各页 aside |

---

## 5. 数据层规范

- 单一入口：`lib/api.ts`（保留现有 `ApiError` / `apiFetch` 契约）。
- 域模块：`domains/<d>/api.ts` 导出强类型函数，**组件不得直接调 `getJSON`**。
- 查询工厂：`hooks/useQuery.ts`（`useState + 缓存 Map + useSyncExternalStore`），提供 `{data, state, refetch}`；`state ∈ loading|success|empty|error`。
- 失效：沿用 `hooks/realtime.ts` 的 SSE 事件名，`collect_done` → 对应域 `invalidate(key)`。
- 页面上每个数据区块最多一个加载态，`partial` 用区块级 `AsyncState` 表达，不允许整页空白。

---

## 6. 分批计划与退出条件

> 每批独立可发布；批内不跨域改动。

| 批 | 内容 | 退出条件 |
|---|---|---|
| **B0** | 覆盖率基线实测（`vitest run --coverage` 存档）；首屏 JS gzip 基线；目录骨架；本文档冻结 | 基线数字入档 `docs/audit/FRONTEND_REWRITE_BASELINE_2026-11-17.md`；`tsc` 绿；包体积不变 |
| **B1** | `tokens.css` 建立（全局 token 单一源，`index.css` 以 `@import` 引入，视觉零变化）+ L1 primitives 八件 + colocated 测试 | 每原子 ≥1 测试；无业务依赖；token 重复定义归零 |
| **B2** | `shell/AppShell` 原地替换 `SentinelShell`（四菜单 + 心跳条 + 主题 + 全局 Toast 提到根） | `nav4_shell` 守卫测试改造后绿；三态主题可切换；旧页在 `--sn-*` 别名下正常渲染 |
| **B3** | `hooks/useQuery` + 域 API 模块；54 处直调收敛 | 直调计数降为 0（grep 断言）；无回归 |
| **B4** | 资讯域 `/` 重写（拆 God 组件 + 密度重排） | 首屏区块全保留；单文件 ≤300 行；包体积不增 |
| **B5** | 知识域 `/knowledge` + 行动域 `/action` 重写 | 同上 |
| **B5.6** | 行动/知识域剩余超限文件拆分（owner 裁决扩批：`EventsReviewPage` / `WeeklyReport` / `MonthlyReport` / `SkillBuilder` / `Dashboard` / `DeepReaderPage` / `NoteEditor`） | 同上 |
| **B5.5** | 首屏瘦身专项（Google Fonts 非阻塞 + i18n 词条按 locale 动态加载 + 归因工具入仓） | **LCP ≤ 基线 80%（唯一判定指标，R4）**；首屏 JS 体积登记且不高于基线 |
| **B6** | 设置域 `/settings` + 工具页容器统一 + 旧三份 CSS 删除 + **组件层剩余超限文件拆分**（`MaintPage` / `ItemDetailDialog` / `DeepReadPage` / `V1Prototype` / `HistoryPage` / `LayerCard` / `TodoItem` / `settings/*` / `secrets/SecretsPage` / `secnews/settings/*` 等 17 件；R3 组件层零豁免）+ 性能对比 + 验证报告 | §7 全部指标达标；旧代码零残留 |
| **B8** | 缺口收口批：**G3**（`EmptyState` / `Toast` / `ErrorBoundary` / `Icon` 迁入 L1 `primitives/`）+ **G4**（`SentinelShell` 兼容桥物理删除，6 处 import 改指 `src/shell/*`）+ **G5**（`api/settings.ts` 847 行按章节拆为薄 barrel + 11 子模块） | 三项缺口关闭；门禁全绿；R4 LCP 单指标达标；体积登记且不得高于基线 |
| **B9** | 遗留项收口批：**a** 设置域子模块 11 → 5 合并（回收 Rollup 共享 chunk）+ **b** 新增 L1 原子 `ToolPageHeader`（compact/bar 两体例），6 页工具页头收敛 + **c** 视觉回归机检工具入仓（`perf/visual_regress.mjs`，补齐仓库无视觉基线的空缺） | chunk 数回落；页头 DOM 逐字节不变；6 路由整页截图与对照构建像素级零差异；门禁全绿；R4 LCP 达标 |

**回滚**: 每批一个 commit（可含 1–3 个配套 commit），回滚 = `git revert` 单批，不依赖跨批状态。

**批次进度**（随批更新；证据统一在 `docs/audit/FRONTEND_REWRITE_VERIFY_2026-11-17.md`）:

| 批 | 状态 | 完成日 | 证据 |
|---|---|---|---|
| B0 | ✅ | 2026-11-17 | 基线存档 §1–§3；DEV-0391 |
| B1 | ✅ | 2026-11-17 | 验证报告 §2；DEV-0392 |
| B2 | ✅ | 2026-11-17 | 验证报告 §3；DEV-0393（缺口见 §4） |
| B3 | ✅ | 2026-11-17 | 验证报告 §5；DEV-0394（缺口 G5/G6 见 §4，偏差 D1–D5 见 §5.5） |
| B4 | ✅ | 2026-11-18 | 验证报告 §8（含 §8.5 D7 关闭记录）；DEV-0395 + DEV-0396（退出条件 3 已由 DEV-0396 复测达标：首屏 JS 92,758 B / 较 B3 −759 B；D6 见 §8.4） |
| B5 | ◐ | 2026-11-18 | 验证报告 §9（点名三文件）+ §10（续拆 9 件，38 新建）；DEV-0397 + DEV-0398；**12 个超限容器全部达标**；域内余 7 件 → B5.6 |
| B5.6 | ✅ | 2026-11-18 | 验证报告 §11（7 个超限文件拆分达标 + R3 契约冲突裁决）；DEV-0399 |
| B5.5 | ✅ | 2026-11-18 | 验证报告 §12（归因工具入仓 + 字体非阻塞 LCP 128ms 达标 + i18n 按 locale 动态加载 + R4 口径降级）；DEV-0400 |
| B6 | ✅ | 2026-11-19 | 拆四子批：**a** 组件层剩余超限（8 件）/ **b** 设置域 /settings / **c** 工具页容器 / **d** 旧三份 CSS 收尾 + 性能对比 + 终章。**a 已交付**：验证报告 §14（8 件拆分，**全站组件层超限清零**；余 10 件全为 R3 契约层），DEV-0402；**b 已交付**：验证报告 §13（业务流三组 IA + 9 件拆分，settings 域超限清零），DEV-0401；**d 已交付**：验证报告 §15（`sentinel.css` 607 → `shell/shell.css` 275 + `sentinel.css` 358，壳层/资讯域按业务流归属，构建产物三路分流实测；守卫改拼接后强度不变），DEV-0403；**c 已交付**：验证报告 §16（口径 A：3 个 skills 页删重复 `p-4 md:p-6`，页边距统一由 PageLayout 提供，内容列宽 1400/900/800 保留；全仓仅这 3 处双重容器），DEV-0404 —— **B6 四子批全部交付，批次关闭** |
| B7 | ✅ | 2026-11-19 | redesign-v1 落地（蓝本 `design/redesign-v1/DESIGN.md` §5 R-1~R-4）。**R-1 已交付**：tokens 补 `--shell-w` / `--dur-*` / `--info` / `*-weak` 别名，`--line-strong` 三态对齐 demo（light 0.28 / dark 0.30 / paper `#cfc6b4`）。**R-2 种子已交付**：`primitives/primitives.css`（26 行）只补 `.badge` 五档语义徽章——**返工记录**：首版按 demo 类名新建 `.pg-head` / `.sec-title` / `.card` / `.stamp` / `.empty4`（137 行），grep 发现 `.ed-*` 已是成熟词汇（ed-head ≈ pg-head、ed-sechead ≈ sec-title、ed-card ≈ card），判定平行双轨**全部撤回**；`PageHeader.tsx` 改为直接复用 `.ed-head / .ed-h1 / .ed-sub`，并补 `kicker`（`.ed-kicker` 眉标）/ `footer`（描述下尾注，承载数据源印章）两个可选 prop；`StatusBadge.tsx` 吃 `.badge + .b-*`；实页接入 **6 处**：`/dashboard`（去自有 `p-6` 双重边距）、`/maint`、`/quality`（PROOFROOM 校对室）、`/knowledge/library`（CATALOG ROOM 编目室）、`/knowledge`（KNOWLEDGE HUB 资料库前厅）、`/events`（WIRE DESK 通稿审核）——后四者收敛后 DOM 顺序与类名逐字不变（kicker→h1→sub→印章）。`PageHeader.test.tsx` 4 → 5 tests。**明确不改**：`/tags` `/search` `/extract` 紧凑工具页头、`/action` `ac-h1`、`/settings` `st-title`、`ReviewPage` 内联 topBar（域内自有版式，换大标题是视觉倒退）。**R-3 / R-4 无需改动**：`Stamp.tsx` 已存在且被 7 处引用（含 test）、壳层已与 demo 同构。**返工二（孤儿原语，收尾审计抓出并修复）**：首版 `StatusBadge.tsx` 全仓零生产消费者（仅自带 test 引用），Vite tree-shake 后整模块连同 `primitives.css` 被丢弃 —— 产物 6 个 CSS chunk 全部 `badge.b-ok:false`（词汇「声明了但没发布」）。修复：①`components/sync/SyncStatusBadge.tsx` 改为 `primitives/StatusBadge` 薄封装（success→ok / error→risk / skipped→warn / unknown→neutral，调用方零改动）；②`components/TodoItem.tsx` 分类 chip 由裸 `.badge` 改为 `.tag`（demo §3 分类标签语义，化解与状态徽章的类名冲突）；③`.b-part` 底色改 `color-mix(in srgb, var(--info) 10%, transparent)`（`--info-weak` 实为薄荷 tint，与 `--info` 色相错配）。**门禁**：`tsc` 0 · **784 tests 全通过** · `vite build` 0；首屏 JS 88,294 → **88,346 B（+52 B，累计 −4,652 B / −5.00%）**，全量 564,612 B / 77 chunk，首屏 CSS 12,754 B 零增长（徽章进入 `index-Cm1W9lCe.css` 306 B gzip，仅 `/sync` 动态加载）。**未做**：其余手写 `<h1>` 接入、LCP 复测（无首屏依赖变化）；验证报告 §17.1–§17.8；DEV-0405 |
| B8 | ✅ | 2026-11-19 | 缺口收口批（G3 / G4 / G5 补做，三子批 a/b/c）。**a（G4）**：`SentinelShell` 兼容桥（9 行）**物理删除**，6 处生产 import 全量改指 `src/shell/*`（`SentinelShell` → `shell/AppShell`，`usePipe` / `usePipeReloadOnSse` → `shell/pipe`），测试迁至 `shell/AppShell.test.tsx`（10 用例逐字未改）；`nav4_shell` 守卫的 `SHELL_FILES` 本就指向 `src/shell/*`，**断言条目与强度零变动**。**b（G3）**：`EmptyState`（109）/ `Toast`（237）/ `ErrorBoundary`（112）/ `Icon`（35）+ 4 个 colocated test 迁入 `primitives/`，**86 处 import 在 81 个文件改指**（脚本按各文件目录深度精确计算相对路径，非文本替换）；迁入件内部依赖仅 `react` + 同目录 `./Icon`，满足 B1「无业务依赖」；每原子仍带 ≥1 测试。**c（G5）**：`api/settings.ts` **847 → 22 行薄 barrel + 11 个子模块**（按原文件章节注释边界切分，最大 134 行）；**82 函数名与导出类型全集 `diff` 零丢失**；barrel 用 `export *` 转发，**126 处消费方 import 路径全部不变**；`nav4_shell` 的 maintenance 端点断言改为对「域模块集合」拼接断言（5 条断言逐条保留，同 B6-d CSS 先例）。**门禁**：`tsc` 0 · **110 文件 / 784 tests 全通过**（用例零增删）· `vite build` 0 · `generate_meta --check` OK；覆盖率 **58.67 / 77.42 / 60.43 / 58.67**（B7 同机实测基线 58.70 / 77.51 / 60.30 / 58.70，Δ ≤0.09 pp，阈值未破）。**体积**：首屏 JS 88,346 → **88,413 B（+67 B，累计 −4,585 B / −4.93%）**，首屏 CSS 12,754 B 零增长；全量 564,612 → **565,046 B / 77 → 81 chunk**，归因 = settings 子模块被多路由共享 → Rollup 拆出 5 个共享 chunk（ops/overview/secrets/skillRegistry/sync = 1,857 B）− 消失 1 个（`settings` 1,848 B），**代码总量仅 +434 B（+0.08%）**。**LCP**：`lcp_ab.mjs --runs=3` × 2 会话，with_fonts 中位 **140 / 152**、no_fonts 中位 **124 / 160** ms（基线 252 ms，目标 ≤201.6 ms）→ **达标**。**§4 缺口表 G3/G4/G5 三行同步改判为已关闭**；验证报告 §19.1–§19.7；DEV-0406 |
| B9 | ✅ | 2026-11-19 | 遗留项收口批（三子批 a/b/c）。**a**：设置域子模块 **11 → 5**（按业务域合并为 `core` 197 / `ops` 200 / `security` 201 / `intelligence` 257 / `knowledge` 34 行，全部 ≤300）；**82 函数名 + 导出类型 + 53 个端点 URL 三重全集 `diff` 零丢失**；barrel `export *` 转发，126 处消费方 import 路径不变；`nav4_shell` 的 `SETTINGS_MODULES` 清单同步为 5 个模块名（断言条目与强度不变）。**b**：新增 L1 原子 `primitives/ToolPageHeader.tsx`（compact / bar 两体例，DOM 与类名逐字复刻原页内实现），收敛 6 页重复页头块 —— `/tags` `/search` `/extract` 三页紧凑头（**原本除前缀 TAG/FIND/EXT 与标题外逐字相同**）+ skills 三页横条头（`SkillStore` / `SkillDetail` / `SkillBuilder`）；原 `Icon` import 随之失效清理；原子自带 colocated test **7 用例**。**c**：新增 `frontend/perf/visual_regress.mjs` —— 逐页截图 + 页头 DOM 导出工具入仓（B5.5「归因工具入仓」先例），并**屏蔽壳层时钟/动画**消除非确定性。**门禁**：`tsc` 0 · **111 文件 / 791 tests 全通过**（+1 文件 +7 用例）· `vite build` 0 · `generate_meta --check` OK；覆盖率 **58.73 / 77.50 / 60.41 / 58.73**（B8 为 58.67 / 77.42 / 60.43 / 58.67，Δ ≤0.08 pp，阈值未破）。**体积**：首屏 JS 88,413 → **88,404 B（−9 B，累计 −4,594 B / −4.94%）**，首屏 CSS 12,754 B 零增长；全量 565,046 → **565,011 B / 81 → 80 chunk**（settings 共享 chunk **5 → 3**：`overview`/`sync`→`core` 541、`ops`/`intake`/`skillRegistry`→`ops` 707、`secrets`/`proxy`→`security` 546；新增 `ToolPageHeader` 共享 chunk 633 B 抵掉 6 页各自的页头内联码，净 −1 chunk / −35 B）。**视觉回归机检（补齐仓库无视觉基线）**：同构建两次截图逐字节一致（确定性成立）→ B8 对照构建 vs B9 六个路由（`/tags` `/search` `/extract` `/skill-store` `/skill-store/new` `/skill-store/:id`）整页截图**逐字节完全一致**，页头 `outerHTML` **逐字节完全一致** → 像素级零变化。**LCP**：`lcp_ab.mjs --runs=3` × 2 会话，with_fonts 中位 **120 / 132** ms、no_fonts 中位 **124 / 120** ms（基线 252 ms，目标 ≤201.6 ms）→ **达标**。**未做**：R-2 词汇表剩余面（各域平行数据表 18 处 / 空态四态 108 文件 / 域内标签 7 处 / 6 件孤儿原语）按 §20.6 登记为缺口 **G7 / G8** 待 owner 裁决，本批不硬改；人工视觉走查仍留白给 owner（机检只覆盖 6 个改动页）；验证报告 §20.1–§20.7；DEV-0407 |


---

## 7. 验收口径

### 7.1 首屏性能 ≥20%（D2 桌面端口径）

- **环境**: 生产构建 `npm run build` + `vite preview`，桌面视口 1440×900，Chromium 冷缓存，同一数据夹具（后端固定响应）。
- **指标（2026-11-18 R4 降级为 LCP 单指标，owner 裁决）**:
  1. **LCP ≤ 基线的 80%**（3 次取中位数）—— **唯一判定指标**；
  2. 首屏 JS 传输体积（gzip）**降级为观测项**，不再作为阻断门禁，但**每批必须登记**，且**不得高于基线**（防止以"反正不判定"为名膨胀）。
- **降级理由（R4）**: 口径 A 目标 74,398 B 中 `vendor-react` 独占 **53,816 B（72.3%）**，属 React 运行时不可压缩项；应用代码预算仅 20,582 B，而 B4 完成态实测 38,942 B（需再砍 47%）。**JS 侧 20% 在架构上结构性不可达** —— 这与 R2 裁决时的前置结论一致，经 B5.5 实测确认。降级后 LCP 仍是硬指标：LCP 原受**阻塞式外部字体 stylesheet** 支配（实测方差达 7.5 s），B5.5 已修复并达 128 ms。
- **基线**: B0 实测存档至 `docs/audit/FRONTEND_REWRITE_BASELINE_2026-11-17.md`。
- **LCP 基线口径修订（R4, 2026-11-18）**: 原基线 252 ms 采于 B3 完成态，**采样时外部字体 CDN 恰好快速响应**，不代表常态（B5.5 实测同环境带字体时中位 448 ms、极值 7,556 ms）。B6 复测须用**同一脚本 + 同一夹具 + 同一网络条件**（`perf/lcp_probe.mjs`），并同时记录带/不带字体两组以区分「代码回归」与「网络抖动」。

### 7.2 测试覆盖率不低于现有

- **基线来源**: B0 实测（当前 `vite.config.ts` 无 coverage 配置，故"现有水平"必须由 B0 建立，不得凭估算）。
- **门禁**: B1 起在 `vite.config.ts` 增加 `coverage.thresholds`，逐域下限 = B0 全局值；任一批不得低于基线。

### 7.3 功能覆盖

- `routes/ROUTE_REGISTRY.md` 全部路由与重定向逐条保留（含 `/judge`→`/`、`/cases`→`/action`、`v1` 四入口 query 透传）。
- PRD 92 条能力覆盖地图（`design/_research/prd-capabilities.md`）逐条可定位到新页面区块；**四向映射基线已产出于 [`audit/PRD_CAPABILITY_MAP_2026-11-18.md`](audit/PRD_CAPABILITY_MAP_2026-11-18.md)**（92 条：已定位 68 / 未定位 24 / 有测试 47），B4–B6 按该表逐域勾选。
- 实现侧不自评 PASS；验收证据写入测试报告，由 owner 复核。

### 7.4 交付物

重构代码 · 变更说明（`docs/CHANGELOG.md` 条目 + DEV_LOG）· 测试验证报告（`docs/audit/FRONTEND_REWRITE_VERIFY_2026-11-17.md`，随各批更新）。

---

## 8. 风险

| 风险 | 缓解 |
|---|---|
| 全量重写击穿 Token 预算 | 严格分批，每批独立交付；预算按 Rule 6 repo-wide 档执行，达 70% 报数并设 checkpoint |
| 旧页在新壳下样式错乱 | 迁移期保留 `--sn-*` → 全局 token 别名。**2026-11-19 改判（Rule 7）**：B6-d 实测壳层硬性已由 CSS 代码分割拆除（`SettingsPage-*.css` 不再含 masthead/headline），`--sn-*` 是 `.sentinel` 作用域内的语义转发层，删除需机械改写 1000+ 处 `var(--sn-*)` 且零功能收益 → **保留不删**（DEV-0403） |
| 守卫测试（源码结构断言）误伤 | `nav4_shell` 在 B2 改造为路由/菜单行为断言，而不是源码字符串匹配 |
| 功能静默丢失 | §7.3 路由与能力双清单逐条勾选；任何未承接项必须在报告中标注为缺口（不隐藏） |