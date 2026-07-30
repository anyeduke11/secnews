# UI/UX 全面重构 · 产品需求文档 (PRD) v1.0

> **版本**: v1.0
> **日期**: 2026-07-21
> **范围**: hotspot v1.7+ 前端 UI/UX 全面重构（Phase 1B-6）
> **已交付**: Phase 1A（commit `4968c7f`，token 补强 + 3 原子 + 嵌套 Layout）
> **部署**: 纯本地单机（单人使用）
> **基线**: 对齐 `ARCHITECTURE.md` / `SPEC.md` / `AGENTS.md` 既有约定

---

## 一、目标与原则

### 1.1 业务目标

| 维度 | 目标 |
|---|---|
| 用户量 | 单人本地使用（同一时刻 1 个客户端） |
| 视觉一致性 | 66 组件 100% 走同一 token 系统，无硬编码颜色 |
| 交互一致性 | 加载/空数据/错误/成功 4 状态统一模式 |
| 主题 | 暗/亮双主题 100% 完整适配 |
| 性能 | vite build < 12s；vitest 75+ 用例 PASS |
| 可维护性 | 6 个 16KB+ 大文件拆分为 ≤ 10KB 子组件 |

### 1.2 设计原则（继承 hotspot 主项目）

1. **本地优先**：无外部字体/图标库依赖，零网络请求
2. **简单胜过复杂**：mono 字体（JetBrains Mono）保持，不引入衬线
3. **语义化 token**：颜色/间距/阴影/z-index/motion/elevation 全部通过 CSS 变量
4. **暗/亮双主题**：所有 token 在 `[data-theme="dark"]` 和 `[data-theme="light"]` 完整定义
5. **零 emoji UI 图标**：统一用 [Icon.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/Icon.tsx) SVG wrapper
6. **a11y 基础**：`aria-label` / `role` / `focus-visible` 已就位（首屏改造必须）
7. **prefers-reduced-motion**：index.css 已尊重，组件不再覆盖

### 1.3 关键决策（已锁定）

| # | 决策 | 来源 |
|---|---|---|
| 1 | 风格: Professional Editorial（mono 保持） | Phase 1A grill |
| 2 | 范围: 全量 66 组件改造 | 用户决策 |
| 3 | 主题: 暗+亮双主题完整适配 | 用户决策 |
| 4 | 字体: 默认 mono, serif 仅 Knowledge 阅读模式预留 | 用户决策 |
| 5 | Token: 仅用 CSS 变量（不引 Tailwind dark: 前缀） | 用户决策 |
| 6 | commit 策略: Phase 1A 已 commit，后续 phase 分批 commit, 最终一次性 push | 用户决策 |
| 7 | 拆分 6 大文件先于 token 化 | 用户决策 |
| 8 | 补 15 高频组件 .test.tsx | 用户决策 |
| 9 | a11y 加固 / 移动端响应式暂缓 | 用户决策（out of scope） |
| 10 | 不引入外部字体 / 不引入 lucide-react | 项目约束（零外部依赖） |

---

## 二、范围

### 2.1 范围内（In Scope）

- **Phase 1B**: 拆 6 个 16KB+ 大文件为 ≤ 10KB 子组件
- **Phase 2**: SecNews 热点聚合 4 组件改造
- **Phase 3**: Knowledge 知识库 3 组件改造
- **Phase 4**: CodeGarden 项目管理 5 组件改造
- **Phase 5**: 系统/工具页 3 组件改造
- **Phase 6**: 测试 + 验证 + 一次性 push

### 2.2 范围外（Out of Scope，本次明确不做）

- ❌ AI 协作功能（M7-M12，CodeGarden Phase 2c）
- ❌ 项目归档 30 天自动停止服务（CodeGarden Phase 2d）
- ❌ 跨机服务网格
- ❌ a11y 加固（仅基础 `aria-label` / `role`）
- ❌ 移动端响应式（仅 5 个高频页 375px 适配，剩余不动）
- ❌ shadcn/ui 引入
- ❌ 国际化 i18n
- ❌ 引入外部字体（Newsreader 已在 `fontFamily.serif` 预留，按需启用）

---

## 三、设计系统现状（Phase 1A 已交付）

### 3.1 Token 补强清单

| Token | 用途 | 状态 |
|---|---|---|
| `--color-*` (6 分类色) | 资讯分类标识 | ✅ 已有 |
| `--bg-primary/card/hover/elevated` | 表面层级 | ✅ 已有 |
| `--border-color/subtle` | 边框 | ✅ 已有 |
| `--text-primary/secondary/muted` | 文字 | ✅ 已有 |
| `--accent-highlight` | 高亮 | ✅ 已有 |
| `--shadow-card/elevated` | 卡片阴影 | ✅ 已有 |
| `--radius-sm/md/lg/full` | 圆角 | ✅ 已有 |
| `--color-success/warning/error/info` | 状态色 | ✅ Phase 1A 新增 |
| `--shadow-popover/modal/toast` | 浮层阴影 | ✅ Phase 1A 新增 |
| `--ease-out/in-out`, `--duration-fast/normal/slow` | 动效 | ✅ Phase 1A 新增 |
| `--space-0..8` (4px base) | 间距 | ✅ Phase 1A 新增 |
| `--z-base..tooltip` (8 级) | z-index | ✅ Phase 1A 新增 |

### 3.2 原子组件清单

| 组件 | 文件 | 用途 | 状态 |
|---|---|---|---|
| EmptyState | [EmptyState.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/EmptyState.tsx) | 空数据占位 | ✅ Phase 1A |
| ErrorBoundary | [ErrorBoundary.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/ErrorBoundary.tsx) | 错误边界 | ✅ Phase 1A |
| Toast + ToastProvider | [Toast.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/Toast.tsx) | 全局通知 | ✅ Phase 1A |
| PageLayout | [PageLayout.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/PageLayout.tsx) | 嵌套 Layout | ✅ Phase 1A |
| useGoHome hook | [useGoHome.ts](file:///Users/duke/Documents/hotspot/frontend/src/hooks/useGoHome.ts) | 路由辅助 | ✅ Phase 1A |

### 3.3 Tailwind 完整映射

[tailwind.config.js](file:///Users/duke/Documents/hotspot/frontend/tailwind.config.js) 完整覆盖 7 类 token（color/font/radius/shadow/space/z-index/transition），组件可通过 `bg-card` / `text-main` / `r-md` / `shadow-card` / `z-modal` 等语义类名引用。

---

## 四、待改造组件矩阵（66 个）

### 4.1 Phase 1B: 拆 6 大文件（优先）

| 文件 | 当前大小 | 拆分方案 | 目标 |
|---|---|---|---|
| [SyncPage.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/SyncPage.tsx) | 33,175B / 868 行 | SyncPage + SyncStatusPanel + SyncBundleConfig + SyncHistory | 4 文件，每 ≤ 10KB |
| [SettingsPanel.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/SettingsPanel.tsx) | 29,798B / 780 行 | SettingsPanel + ThemeSettings + RefreshSettings + DisplaySettings | 4 文件 |
| [FavoritesPanel.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/FavoritesPanel.tsx) | 16,249B / 425 行 | FavoritesPanel + FavoriteList + FavoriteItem + FavoriteToolbar | 4 文件 |
| [codegarden/ServiceMesh.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/codegarden/ServiceMesh.tsx) | 16,674B / 437 行 | ServiceMesh + ServiceCard + ServiceDetail + ServiceFilters | 4 文件 |
| [codegarden/DependencyGraph.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/codegarden/DependencyGraph.tsx) | 16,043B / 420 行 | DependencyGraph + GraphNode + GraphEdge + ImpactPanel | 4 文件 |
| [codegarden/ResourceHub.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/codegarden/ResourceHub.tsx) | 15,028B / 393 行 | ResourceHub + PortPool + EnvTemplateList + VolumeManager | 4 文件 |

**拆分原则**：
- 单文件 ≤ 10KB / ≤ 300 行
- 子组件接收 props 而非 import 全局状态
- 子组件可独立测试（最低 .test.tsx 覆盖渲染 + 关键交互）
- 重命名 `xxx.tsx` → `xxx/index.tsx` 仅当形成"目录 + 多个子文件"时

### 4.2 Phase 2: SecNews 热点聚合（4 组件）

| 组件 | 文件 | 改造重点 |
|---|---|---|
| HotspotCard | [HotspotCard.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/HotspotCard.tsx) | 6 分类色 token 化 + hover/active 状态统一 |
| HotspotGrid | [HotspotGrid.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/HotspotGrid.tsx) | Loading/Empty/Error 三态 + 分页 token 化 |
| TrendChart | [TrendChart.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/TrendChart.tsx) | ECharts 暗/亮主题切换（颜色引用 token） |
| SearchBar | [SearchBar.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/SearchBar.tsx) | focus-ring / 暗/亮 input 样式 |

**改造规则**：
- 硬编码 `#xxx` 颜色 → `var(--color-*)` 或 Tailwind `text-main` / `bg-card`
- `style={{ color: 'var(--text-*)' }}` → Tailwind `text-*` 类名
- "暂无数据"文案 → `<EmptyState title="..." description="..." />`
- Loading 占位 → `<LoadingSkeleton />` 或组件内置

### 4.3 Phase 3: Knowledge 知识库（3 组件）

| 组件 | 文件 | 改造重点 |
|---|---|---|
| KnowledgeGraph | [KnowledgeGraph.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/KnowledgeGraph.tsx) | Recharts 暗/亮主题 + 节点色用 cat-* |
| KnowledgePage | [KnowledgePage.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/KnowledgePage.tsx) | EmptyState 接入 + 列表 token 化 |
| LearningPanel | [LearningPanel.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/LearningPanel.tsx) | MasteryGauge 暗/亮适配 |

### 4.4 Phase 4: CodeGarden（5 组件 Phase 2b）

| 组件 | 文件 | 改造重点 |
|---|---|---|
| CodegardenPage | [CodegardenPage.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/CodegardenPage.tsx) | ProjectCard/ProjectList 状态统一 |
| CodegardenPhase2bPage | [CodegardenPhase2bPage.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/CodegardenPhase2bPage.tsx) | Tab 切换动效 token 化 |
| ServiceTopology | [ServiceTopology.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/codegarden/ServiceTopology.tsx) | SVG 拓扑颜色用 cat-* |
| EventBus | [EventBus.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/codegarden/EventBus.tsx) | 事件流 token 化 + 状态色（success/warning/error） |
| PlaybookList | [PlaybookList.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/codegarden/PlaybookList.tsx) | YAML 渲染 monospace token 化 |

### 4.5 Phase 5: 系统/工具页（3 组件）

| 组件 | 文件 | 改造重点 |
|---|---|---|
| HealthDashboard | [HealthDashboard.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/HealthDashboard.tsx) | 状态色（success/warning/error）应用 |
| HistoryPage | [HistoryPage.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/HistoryPage.tsx) | EmptyState 接入 + onBack 移除 |
| TodosPage | [TodosPage.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/TodosPage.tsx) | onBack → useGoHome + Toast 接入 |

### 4.6 其余 45 组件（按需改造）

不在 1B/2-5 强制范围的组件**采用最小改动**：
- 仅替换硬编码颜色 → token
- 不改业务逻辑
- 不重写测试（除非破坏）
- 累计 45 文件，每文件 ≤ 50 行 diff

按"完成度优先级"：高频可见组件 > 工具型组件 > 一次性页面

---

## 五、测试补强清单（15 个）

按"高频优先"原则：

| # | 组件 | 测试类型 | 优先级 |
|---|---|---|---|
| 1 | SyncPage | 拆分后子组件 render + 交互 | P0 |
| 2 | SettingsPanel | 拆分后子组件 render | P0 |
| 3 | FavoritesPanel | 拆分后子组件 render | P0 |
| 4 | codegarden/ServiceMesh | 拆分 + 已有 .test.tsx 扩展 | P0 |
| 5 | codegarden/DependencyGraph | 拆分 + 已有 .test.tsx 扩展 | P0 |
| 6 | codegarden/ResourceHub | 拆分 + 已有 .test.tsx 扩展 | P0 |
| 7 | EmptyState | 新建，render + 变体 | P1 |
| 8 | ErrorBoundary | 新建，throw + 恢复 | P1 |
| 9 | Toast | 新建，show + dismiss | P1 |
| 10 | PageLayout | 新建，render + Outlet | P1 |
| 11 | useGoHome | 新建，hook 测试 | P2 |
| 12 | HotspotCard | render + 收藏切换 | P1 |
| 13 | HotspotGrid | Empty/Loading 状态 | P1 |
| 14 | TrendChart | 暗/亮主题切换 | P2 |
| 15 | KnowledgeGraph | 节点 + 边 render | P2 |

**测试规则**：
- 已有 .test.tsx → 扩展 case 覆盖新拆分子组件
- 失败测试先**评估**是测试期望过期还是代码 bug（Rule 7 + Rule 9）
- 不批量自动更新 snapshot（Rule 9：测试验证 intent）

---

## 六、验收标准

### 6.1 强制验收（必须 100% 通过）

| # | 标准 | 测量方法 |
|---|---|---|
| 1 | `tsc --noEmit` 0 错误 | `cd frontend && npx tsc --noEmit` |
| 2 | `vitest run` 全 PASS | `cd frontend && npx vitest run` |
| 3 | `vite build` < 12s 成功 | `cd frontend && npm run build` |
| 4 | 硬编码颜色（除注释）= 0 | `grep -rE "#[0-9a-fA-F]{3,8}" frontend/src --include="*.tsx" --include="*.ts" --include="*.css" \| grep -v "^\s*//" \| wc -l` |
| 5 | 6 大文件每个 ≤ 10KB | `find frontend/src -name "*.tsx" -size +10k \| wc -l` = 0 |
| 6 | 暗/亮主题切换正常 | 浏览器手动验证 |

### 6.2 软性验收

- 视觉效果与 Phase 1A audit 现状**无回归**
- 加载/空数据/错误 4 状态 100% 走统一组件
- 主题切换无闪烁
- tsc 警告数 ≤ 现状

### 6.3 性能基线

| 指标 | 当前 | 目标 |
|---|---|---|
| vite build 时间 | ~6.91s | < 12s |
| vitest 时间 | ~1.56s | < 3s |
| tsc 时间 | < 5s | < 8s |
| 路由切换体感 | 流畅 | 不退化 |

---

## 七、风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| **R1: 60+ 测试 snapshot 失败** | 高 | 拆分测试类型，**只更新明确过期**的，保留业务逻辑变更的失败（Rule 9） |
| **R2: 一次性 commit 风险** | 高 | 已分阶段 commit（Phase 1A `4968c7f`），后续 phase 独立 commit，最终一次性 push |
| **R3: ECharts 暗/亮主题适配** | 中 | ECharts 实例化时读取 `data-theme` 属性，setOption 切换 |
| **R4: 大文件拆分引入 import 循环** | 中 | 拆分前先建依赖图，子组件仅向上 import，共享类型抽 `types/` |
| **R5: 暗/亮主题色对比度** | 中 | 借用 ui-ux-pro-max 规则：暗模式 text-primary ≥ 4.5:1 |
| **R6: onBack 移除影响 12 page** | 中 | Phase 1A 已加 `useGoHome` hook，渐进迁移（先 5 个高频，再 7 个） |
| **R7: TS strict 模式新警告** | 低 | 复用现有 tsconfig，不引入新 strict 选项 |
| **R8: Token 命名冲突** | 低 | 统一前缀：颜色 `color-`/`cat-`，表面 `bg-`/`dark-`，状态 `success`/`warning` |

---

## 八、实施路线（8 个 Phase）

### Phase 1A: 设计系统骨架（已交付 ✅）

- ✅ Token 补强（index.css + tailwind.config.js）
- ✅ 3 个原子组件（EmptyState/ErrorBoundary/Toast）
- ✅ 嵌套 Layout（PageLayout + App.tsx）
- ✅ useGoHome hook
- ✅ tsc 0 错误 / vitest 75/75 PASS
- ✅ Commit: `4968c7f`

### Phase 1B: 拆 6 大文件（下一步）

**目标**：6 大文件拆分为 24 个子组件（每文件 ≤ 10KB）

**步骤**：
1. 读 [SyncPage.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/SyncPage.tsx) 完整内容
2. 识别内聚的逻辑段（如配置/状态/历史/操作）
3. 抽子组件 + 子 hook（如 useSyncBundle）
4. 验证 tsc + vitest
5. 对 5 大文件重复步骤 1-4
6. 独立 commit: `refactor(frontend): split 6 large files into subcomponents`

**完成标准**：每文件 ≤ 10KB，子组件独立可测

### Phase 2: SecNews 热点聚合（4 组件）

**目标**：HotspotCard / HotspotGrid / TrendChart / SearchBar 全部 token 化

**步骤**：
1. 替换硬编码颜色 → token
2. 接入 EmptyState / LoadingSkeleton
3. TrendChart ECharts 主题 token 化
4. SearchBar focus-ring 应用
5. 验证 + commit

### Phase 3: Knowledge 知识库（3 组件）

**目标**：KnowledgeGraph / KnowledgePage / LearningPanel 全部 token 化

**步骤**：
1. Recharts 暗/亮主题适配
2. KnowledgePage EmptyState 接入
3. MasteryGauge token 化
4. 验证 + commit

### Phase 4: CodeGarden（5 组件）

**目标**：5 个 Phase 2b 组件 token 化

**步骤**：
1. ServiceTopology SVG 颜色 token 化
2. EventBus 状态色（success/warning/error）应用
3. PlaybookList monospace token 化
4. CodegardenPage / Phase2bPage Tab 动效 token 化
5. 验证 + commit

### Phase 5: 系统/工具页（3 组件 + 45 组件最小改动）

**目标**：剩余组件最小改动

**步骤**：
1. HealthDashboard / HistoryPage / TodosPage token 化 + onBack 移除
2. 45 组件批量 token 化（≤ 50 行/文件）
3. 验证 + commit

### Phase 6: 测试补强（15 个）

**目标**：15 高频组件 .test.tsx 覆盖

**步骤**：
1. 6 大文件拆分后的子组件测试（6 个）
2. 3 原子组件测试（3 个）
3. PageLayout + useGoHome 测试（2 个）
4. 4 个高频组件扩展测试（4 个）
5. 验证 + commit

### Phase 7: 验证 + 一次性 push

**目标**：origin main 推送

**步骤**：
1. 全量 tsc + vitest + vite build 验证
2. 浏览器手动验证暗/亮双主题
3. 敏感文件核查（.env / proxy_config / hotspot.db）
4. 一次性 commit: `chore: UI/UX refactor complete (Phase 1A-6)`
5. `git push -u origin main`

---

## 九、决策日志（Decision Log）

| 决策 | 选项 | 选定 | 理由 |
|---|---|---|---|
| 设计风格 | Editorial / Mono 保持 / Cyberpunk | **Mono 保持** | 项目固 mono 风格 (JetBrains Mono) |
| 改造范围 | 23 组件 / 66 组件 / 仅设计系统 | **66 组件** | 用户决策 |
| 主题交付 | 单主题 / 双主题 | **双主题** | 用户决策 |
| Token 表达 | CSS 变量 / Tailwind dark: | **CSS 变量** | 现状已用，避免双轨 |
| 大文件处理 | 拆/不拆 | **先拆再做** | 治理优先，质量高 |
| 一次性 commit | 是/分阶段 | **分阶段 commit + 最终一次性 push** | 平衡风险 + 用户需求 |
| a11y | 加固/基础/不做 | **基础** | 用户决策（Phase 7 暂缓） |
| 移动端 | 全量/5 页/不做 | **不做** | 用户决策（暂缓） |
| 外部字体 | 引入/不引入 | **不引入** | 项目零外部依赖约束 |

---

## 十、目标验证清单（Goal-Driven）

按 `goal` 模式完成 Phase 1B-7 时，**逐项勾选**：

```
[ ] Phase 1B: 6 大文件拆分完成, 每文件 ≤ 10KB
[ ] Phase 2: SecNews 4 组件全部 token 化
[ ] Phase 3: Knowledge 3 组件全部 token 化
[ ] Phase 4: CodeGarden 5 组件全部 token 化
[ ] Phase 5: 系统页 3 组件 + 45 组件最小改动完成
[ ] Phase 6: 15 个 .test.tsx 全部 PASS
[ ] Phase 7: tsc 0 / vitest 75+ / vite build < 12s / 浏览器验证
[ ] Phase 7: 一次性 push origin main 成功
[ ] 0 硬编码颜色 / 0 emoji UI 图标 / 100% 走 token 系统
[ ] 暗/亮双主题完整适配, 0 闪烁
```

**完成定义（Definition of Done）**：
- 上述所有复选框 ✅
- 一次性 commit `chore: UI/UX refactor complete` 推送 origin
- 浏览器手动验证暗/亮双主题无视觉回归
- 后端 1283 测试 + 前端 75+ 测试全 PASS
- 敏感文件 0 误提交

---

## 十一、参考与链接

- [SPEC.md v3.1](file:///Users/duke/Documents/hotspot/docs/SPEC.md) — 功能规范
- [ARCHITECTURE.md v3.0](file:///Users/duke/Documents/hotspot/docs/ARCHITECTURE.md) — 架构
- [AGENTS.md](file:///Users/duke/Documents/hotspot/AGENTS.md) — AI 协作规则
- [CLAUDE.md](file:///Users/duke/Documents/hotspot/CLAUDE.md) — Claude Code 协作规则
- [Phase 1A commit](https://github.com/anyeduke11/secnews) — `4968c7f`
- [index.css](file:///Users/duke/Documents/hotspot/frontend/src/index.css) — Token 定义
- [tailwind.config.js](file:///Users/duke/Documents/hotspot/frontend/tailwind.config.js) — Tailwind 映射
- [PageLayout.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/PageLayout.tsx) — 嵌套 Layout
- [EmptyState.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/EmptyState.tsx) — 原子 1/3
- [ErrorBoundary.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/ErrorBoundary.tsx) — 原子 2/3
- [Toast.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/Toast.tsx) — 原子 3/3
