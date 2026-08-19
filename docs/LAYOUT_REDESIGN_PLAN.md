# Hotspot 界面改造计划

> 全站界面优化的总纲。配套 `scripts/layout-backup.sh` + `scripts/layout-restore.sh` 使用。

## 总目标

- 范围：**全站所有功能**（SecNews / Knowledge / CodeGarden / ActionLayer / JudgeLayer / Report / Settings / Sync / Secrets / Skills / Quality / History / Todos）
- 改造深度：**视觉 + 区块 + 动线重构**（含视觉层 + JSX 结构 + 关键交互入口）
- 范围边界：**只动 frontend/** 与少量 `docs/` 文档；不动 `backend/`、`knowledge/*.md`、`codegarden/`、`config/`
- 核心诉求：信息层级梳理 / 区块分布与留白 / 操作动线 / 不同屏幕适配，每处调整单独讲清理由

## 当前项目基线（2026-08-18 快照）

- 项目：`hotspot-map` v0.4.3
- 栈：React 18 + Vite 5 + Tailwind v3.4 + TypeScript 5.3
- 图表：echarts 6 + recharts 3.9
- 字体：JetBrains Mono（主）+ Inter（sans）+ Newsreader（serif）
- 设计哲学：等宽主字体 + 暗色技术美学（PRD 默认暗色，亮色独立色板）
- 路由架构：3 层架构（`/data` + `/judge` + `/action`）+ 知识库 12 子路由 + CodeGarden + Report + 兼容旧路由
- 体量：**207 个 .tsx / 35,792 行 / 11 个组件族**
- 自动化测试：vitest 286+ 用例
- 既有 git 改动：3886 个文件（含 v0.4.3 计划系列文档/PRD/knowledge 草稿），已 backup 到 `backup/stage-0-init-20260818-165119`

## 既有设计 Token（已抽出）

### 颜色
- 暗色 `bg-primary #0a0a0f` / `bg-card #111118` / `bg-hover #181825` / `bg-elevated #1c1c2e`
- 亮色 `bg-primary #f4f4f8` / `bg-card #ffffff` / `bg-hover #eeeef4`
- 暗色 accent `#00bcd4`（青） / 亮色 accent `#00acc1`
- 7 分类色：`ai`（青）`security`（红）`finance`（金）`startup`（紫）`bid`（橙）`general`（绿）`github`（淡紫）
- 3 层架构色：`data`（青）`judge`（金）`action`（绿）
- 状态色：`success` `warning` `error` `info`

### 形状
- 圆角：`6 / 10 / 14 / 20 / full` 5 档
- 间距：`4 / 8 / 12 / 16 / 20 / 24 / 32 / 40`
- Z-index：`0 / 100 / 200 / 300 / 400 / 500 / 600 / 700`

### 动效
- 缓动：`cubic-bezier(0.16, 1, 0.3, 1)`（out） + `cubic-bezier(0.4, 0, 0.2, 1)`（in-out）
- 持续时间：`120ms / 200ms / 320ms`
- MOTION_INTENSITY：3（保守，无 parallax 无 scroll-hijack）
- 关键帧：`fade-in-up` / `fade-in` / `scale-in` / `slide-in-*` / `shimmer` / `pulse-dot` / `spin`
- 减动：`@media (prefers-reduced-motion: reduce)` 全局兜底已实现

### 字体尺度
- 全局 base：`13px`（移动端 `14px`）
- 报头 masthead：`18px / 700 / 0.04em tracking`
- feed 标题：`13px / 600`
- 聚簇徽章 / view-more / cluster-badge：`10px / 700 / 0.06em`
- flow-action-label：`11px / 600`
- flow-action-desc：`9px`（极小，可读性风险点）
- 按钮：`11px`（min-height 30px）

## 备份与还原

| 命令 | 作用 |
|---|---|
| `./scripts/layout-backup.sh <stage-name>` | 在新分支 `backup/<stage>-<timestamp>` 上 snapshot 当前工作树（含 uncommitted） |
| `./scripts/layout-restore.sh <stage-name>` | 还原到指定 stage，stash 当前工作，working tree 覆盖，HEAD 不变 |
| `./scripts/layout-restore.sh latest` | 还原到最近一次 backup |
| `./scripts/layout-restore.sh list` | 列出所有 backup |

**当前 backup**：`backup/stage-0-init-20260818-165119` @ `b9306a90`

## 分阶段路线图

| Stage | 范围 | 起点 backup | 当前状态 |
|---|---|---|---|
| 0 | 全局基线 audit | `stage-0-init` | ✅ 已 backup |
| 1 | 全局基础设施（legacy alias 收编、字号 audit、路由拆分） | `stage-1-infra` | 待启动 |
| 2 | SecNews 热点聚合（`/data` 及子路由） | `stage-2-secnews` | 待启动 |
| 3 | Knowledge 知识库（6 模式 + Attention Heatmap） | `stage-3-knowledge` | 待启动 |
| 4 | CodeGarden 项目管理（项目看板 + 服务网格 + 依赖图） | `stage-4-codegarden` | 待启动 |
| 5 | ActionLayer / JudgeLayer / Report / Settings 等辅助页 | `stage-5-aux` | 待启动 |
| 6 | 跨子系统串联 + 暗色/亮色 token 校准 + 移动端断点 + 减动落地 | `stage-6-final` | 待启动 |

每个 Stage 内部统一走：
1. 静态 audit（读代码 / 截图 / 痛点访谈）
2. 改造点清单（每点写明理由 / 影响面 / 风险）
3. **先 backup 再改**（`./scripts/layout-backup.sh stage-N-<scope>`）
4. 分批实施（小粒度 commit，便于部分回退）
5. 用户验收
6. 保留还原能力（`./scripts/layout-restore.sh <stage>` 随时回滚）

## 改造深度分级

本计划全程按 `视觉 + 区块 + 动线重构` 走（即用户选定最深层级），每个改动按以下影响面分类：
- **L0 视觉层**：颜色 / 间距 / 字号 / 圆角 / 阴影（仅 CSS 变量与 utility class）— 风险最低
- **L1 区块层**：JSX 结构 / 容器顺序 / 栅格（动 component tree 但不动 state）— 风险中
- **L2 动线层**：关键操作入口位置 / 跳转路径 / 状态机（动 interaction logic）— 风险高

每条改造点会在 audit 报告里标注 L0/L1/L2。

## 反 slop 自检清单（每次改完走一遍）

- 颜色一致性：所有 accent 用 token，不用 raw hex
- 形状一致性：所有圆角从 5 档选一，不混搭
- 动效一致性：动效只用既有 7 种关键帧，不发明
- 字号下限：正文 ≥ 11px，描述/辅助 ≥ 10px 强警示
- 按钮：min-height 30px，hover/active/disabled 三态完整
- 减动：所有新增动效兜底 `prefers-reduced-motion`
- 可访问性：focus ring 统一 `--accent` outline，2px + 2px offset

## 风险与护栏

- **不动** `backend/` 任何文件
- **不主动改** `*.test.tsx`（测试夹具保持原样）
- **不破坏** 既有 lazy load 切分（54 个 lazy import 保留）
- **不引入** 任何新依赖
- **不改** 路由结构（除非有 fallback 重定向）
- **每次改动前必有 backup**（脚本兜底，不依赖人工纪律）

## 协作约定

- 每个 Stage 启动时，我先静态 audit 一遍，给改造点清单 + 理由 + 风险等级
- 你确认后我开始改
- 每批小改动（通常 1-3 个文件）后告诉你改了哪里、为什么
- 任何时刻你想回滚到任意 Stage 起点，一句话 `restore <stage>` 即可
