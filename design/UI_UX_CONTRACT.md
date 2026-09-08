# Hotspot v1.0 UI/UX Design Contract

> **~~部分废止 (SUPERSEDED 2026-09-08)~~**：本文中壳层/导航条款（四入口、V1SentinelShell、移除管道状态条等）**不再作为实施依据**，由 [`docs/v0.8.5/V0.8.5_PLAN.md`](../v0.8.5/V0.8.5_PLAN.md) 取代（v0.8 SentinelShell 三层为唯一壳，管道心跳条全站常驻）。视觉 token、状态语义、组件密度等与壳无关的条款继续有效。

> **状态**: v1.0.0 重构收尾,UI/UX 落地规范
> **基线**: [docs/v1.0/V1.0.0_UI_UX_SPEC.md](docs/v1.0/V1.0.0_UI_UX_SPEC.md) 落实为可执行设计契约
> **风格**: 参考 [.agents/skills/industrial-brutalist-ui](../.agents/skills/industrial-brutalist-ui/SKILL.md) — 安全数据密集终端,符合 Hotspot 安全工作站定位 (不套用营销页或休闲 UI 模板)
> **日期**: 2026-09-07

## 1. 核心定位

Hotspot 是**安全从业者工作台**。用户主对象是资料、关注对象、事项、判断、行动、成果、经验;dsh/pi 是内部组件,主要在运行详情或系统诊断中显示。

首屏回答 **"今天需要我判断什么、补什么、批准什么、验收什么"**。

六个 Skill (SK-01..06) 以对应业务动作出现,不在前台作为独立 SK 编号选择器;能力中心统一管理。

## 2. 信息架构与 URL

| 路径 | 页面职责 | 关键规则 |
|---|---|---|
| `/` | 默认进入今日工作 | 新工作台验收后切换;过渡期保留旧入口可访问 |
| `/workbench` | 今日待办 + 关键变化 | 不展示运行时仪表盘作为主内容 |
| `/intel` | 精选、待核实、历史资料 | 视图/来源/主题/时间写 URL query |
| `/intel/:signalId` | 事件证据与变化 | 查看多源原文、加入/创建 Case |
| `/cases` | 按工作阶段组织事项 | 列表优先,阶段筛选,支持保存视图 |
| `/cases/:caseId/:section?` | 事项工作区 | section = overview/evidence/judgments/actions/artifacts/review |
| `/knowledge` | 经验与历史资料目录 | published 与待校验历史资料明确分层 |
| `/knowledge/:knowledgeId` | 经验详情、条件与采用 | 预留旧静态子路径(import/process/compile/imported/deep-read),不被动态 ID 吞掉 |
| `/subjects` | 岗位/关注对象与资产版本 | 导入预览、错误行、别名、快照 |
| `/sources` | 信源与采集状态 | 尝试/成功/新内容分开,显示重试原因 |
| `/skill-store` | 能力中心 | 复用现有路径,前台名称为"能力" |
| `/runs/:runId` | 真实运行与成果 | 步骤、模式、版本、日志、取消和恢复 |
| `/settings` | 配置、诊断与维护 | dsh/pi、模型、数据环境、备份 |

**禁止**: 一个应用壳渲染多次主导航/ToastProvider/页头;V1Prototype 内层 4 主入口 tabs 与新导航并存;`/knowledge/import|process|compile/...` 全部重定向到 `/knowledge` 首页(必须按对象身份做兼容跳转)。

刷新/后退必须回到相同对象和筛选,浏览器标题包含当前工作对象。

## 3. 应用壳与视觉规范

### 3.1 布局骨架

```
┌──────────────────────────────────────────────────────────┐
│ Hotspot │ v1.0 │ 今日工作 │ 情报 │ 事项 │ 知识 │ 能力 │ 设置 │  ← AppNav (主导航,固定顶部,1440 高 56px)
├─────┬────────────────────────────────────────────────────┤
│     │  <page header>                                       │
│ Nav │ ─────────────────────────────────────────────────  │
│侧栏 │  <main content>                                     │
│     │  桌面 1440: 双栏证据阅读 / 列表 + 详情            │
│ 240 │  桌面 1280: 单主栏 + 抽屉                           │
│     │  平板 1024: 折叠辅助栏                              │
│     │  移动 768: 单列                                     │
│     │  手机 390: 顶栏 + 顺序步骤                          │
└─────┴────────────────────────────────────────────────────┘
```

### 3.2 设计 token (industrial-brutalist 终端风)

| 项目 | 约束 |
|------|------|
| 字体 | 中文: 现有系统无衬线栈;英文: ui-monospace, "SF Mono", Menlo;数字: `font-variant-numeric: tabular-nums` (等宽数字) |
| 字号 | 正文 14px / 辅助 12px / 页标题 22px / 面板标题 16px / 状态徽章 11px |
| 字距 | 0;不用负字距;不用 vw 字号(布局抖动) |
| 主色 | 黄 #d4a017 (需处理) / 红 #c1272d (失败/风险) / 绿 #1f7a3a (已确认) / 蓝 #2563eb (执行中) — 全部带文字 label,不只靠颜色 |
| 中性色 | bg 浅 `#fafaf7` / 深 `#161616`;线 `#d4d4d0` / `#3a3a3a`;墨 `#1a1a1a` / `#e6e6e3` |
| 圆角 | 控件 4px / 卡片 6px;不嵌套卡片;不做浮动大圆角 |
| 密度 | 表格行 44..48px / 工具栏 40..44px / 输入框 32..36px |
| 边框 | 1px solid var(--line);不靠阴影分层(终端风) |
| 间距 | 4 / 8 / 12 / 16 / 24 / 32 (4px 网格) |
| 图标 | lucide-react 锁版本;nav 用语义图标 (Inbox/BookOpen/Briefcase/Boxes/Sparkles/Settings);禁止 emoji |

### 3.3 关键组件模式

**StatusBadge** (`<span class="badge badge-{kind}">`):
- yellow: 需处理 (CTA 显著)
- red: 失败/风险 (含详细错误)
- green: 已确认 (含时间戳)
- blue: 进行中 (含进度)
- gray: 等待/已折叠

**DataTable** (终端风):
- 表头粘性, 行 44px
- 列宽稳定, 不靠 hover 改变布局
- 数字列右对齐 + tabular-nums
- 空状态: 明确区分 loading / empty / stale / error (4 种)
- 行 hover 仅背景色, 不动尺寸

**ErrorBoundary**:
- 失败卡片红边, 含"重试"和"详情"按钮
- 不展示技术堆栈给用户, 内部 `__dev__` 才显示

**Toast** (已有, T17.5 落地):
- dedupe_key 2s 合并同类
- per-event_type muted Set 落 localStorage.toast_muted
- 不静默吞错, 一律显示 + 链接到详情

**AppNav** (T17.5 落地):
- 桌面: 顶部 56px + 左侧 240-280px SideNav
- 移动: 顶部 48px + 390 宽 Hamburger Drawer
- v1_active 绿色 / legacy 灰度, 4 主入口 + 6 SK 入口 + 4 知识管理入口

## 4. 当前 R24 收尾 (UI/UX SPEC 落地清单)

按 [V1.0.0_UI_UX_SPEC.md §2 信息架构](docs/v1.0/V1.0.0_UI_UX_SPEC.md) 与 §3 视觉规范对照当前 v0.7 Sentinel 壳,本批次收尾:

### 4.1 必做 (L1 服务恢复 + UI 衔接)

- ✅ 后端 8000 起来 + health ok (R21 修复)
- ✅ 前端 8898 代理 8000 (R22 修复)
- ⏳ 4 真路由 (`/workbench` `/intel` `/cases` `/knowledge`) 走 V1Prototype (T15 已落) — 验证入口可达
- ⏳ AppNav 4 主入口 + 6 SK + 4 知识管理 (T17.5 已落) — 验证 UI 显示

### 4.2 必做 (B0 范围, UI 收尾)

- ⏳ 默认 `/` 仍为旧 Sentinel 独立壳 (R24) → 收尾后切换到 `/workbench`
- ⏳ V1Prototype 内层 4 主入口 tabs 与 AppNav 主导航并存 → 收尾后删 V1Prototype tabs
- ⏳ `/knowledge` 重复声明 → 收尾后单一声明, 旧静态子路径兼容跳转
- ⏳ `lucide-react` 锁版本 (替换主导航 emoji) → 收尾后实施

### 4.3 留待 B4 (浏览器可操作闭环)

- ⏳ Case 详情内全部 mutation (创建事项/选择证据/审阅发布/批准行动/启动取消/产物验收/经验采用) → B4 范围
- ⏳ 删除生产 mock fallback (R14) → B4 范围
- ⏳ SSE 真实事件刷新 (R18) → B4 范围

### 4.4 留待 B7 (原标准发布验收)

- ⏳ PRD AC-01..12 / E2E-01..12 全矩阵证据
- ⏳ G1-G5 全部通过
- ⏳ 性能 + 源质量标注 + 浏览器验证

## 5. 与现有 UI 资源的关系

- **V1Prototype.tsx** (T15): 业务数据接入, 4 view 接真实 API;**R24 收尾后删除内层 tabs, 只保留视图内容**
- **AppNav.tsx** (T17.5): 4 主入口 + 6 SK + 4 知识管理 = 14 项 nav;**保留, 作为 L1 应用壳**
- **PageLayout.tsx** (T17.5): 桌面 sm:pl-64 主内容偏移;**保留**
- **Toast.tsx** (T17.5): dedupe_key 2s 合并 + muted Set 落 localStorage;**保留**
- **useSSEWithRefetch.ts** (T17.5): V1Prototype 顶层 useSSE 订阅 5 event_type;**R18 修复后保留并扩展**

## 6. 实施纪律

1. 复用现有 CSS 语义 token, 不另写一套 v1 硬编码背景
2. 真实资料截图、文档预览、实际成果, 不用装饰图冒充证据
3. 数字一律 `tabular-nums` (financial 风), 不与中文混排错位
4. 命令按钮用图标+明确动词 (例: "批准" 而非 "确定")
5. 空状态 4 态 (loading/empty/stale/error) 全部覆盖, 不混用
6. 响应式: 移动端 44px 触控目标, 底部操作条不遮挡正文/软键盘
7. 键盘可达: 可见焦点、Tab 顺序、语义表头、label 与错误关联
8. 对比度: 普通文字 4.5:1, 状态不只靠颜色
9. 动效: 120-200ms 必要过渡, 尊重 `prefers-reduced-motion`
10. 不写新组件前先 grep 已有;不引新依赖前先看 tree-shaking 影响

## 7. 关联

- [docs/v1.0/V1.0.0_CLOSEOUT_PLAN.md](docs/v1.0/V1.0.0_CLOSEOUT_PLAN.md) — 整体收尾方案
- [docs/v1.0/V1.0.0_CLOSEOUT_TASKS.md](docs/v1.0/V1.0.0_CLOSEOUT_TASKS.md) — C01-C14 任务书
- [docs/v1.0/V1.0.0_UI_UX_SPEC.md](docs/v1.0/V1.0.0_UI_UX_SPEC.md) — UI/UX 规范 (源)
- [docs/v1.0/REVIEW_2026-09-07.md](docs/v1.0/REVIEW_2026-09-07.md) — 业务审查 20 P1
- [docs/v1.0/CLOSEOUT_2026-09-07.md](docs/v1.0/CLOSEOUT_2026-09-07.md) — 诚实完结报告
- [.agents/skills/industrial-brutalist-ui](../.agents/skills/industrial-brutalist-ui/SKILL.md) — 风格参考
- [.agents/skills/redesign-existing-projects](../.agents/skills/redesign-existing-projects/SKILL.md) — 现有项目 UI 升级
