# Phase 1B 子 PRD — 拆 6 大文件

> **Master PRD**: [UIUX_REFACTOR_PRD.md](file:///Users/duke/Documents/hotspot/docs/UIUX_REFACTOR_PRD.md) v1.0 §4.1
> **状态**: ⏳ 待开始（Phase 1A 已交付，commit `4968c7f`）
> **Owner**: agent (goal 模式)
> **预计 commit**: `refactor(frontend): split 6 large files into subcomponents`

---

## 0. Goal (一句话)

把 6 个 16KB+ / 300+ 行的大文件，按内聚逻辑拆分为 ≤ 10KB / ≤ 300 行的子组件文件，每个子组件**独立可测、可读、可维护**。

## 1. 入口 / 出口

- **入口**: `frontend/` 当前 `tsc 0` + `vitest 75+ PASS`（Phase 1A 已验证）
- **出口**: 6 大文件均不存在（被目录+子文件替代），子组件文件 ≤ 10KB，`tsc 0` + `vitest 75+ PASS`（数量因新增测试提升）

## 2. In Scope（必须做）

| # | 当前文件 | 目标拆分 | 子文件位置 |
|---|---|---|---|
| 1 | [SyncPage.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/SyncPage.tsx) (862 行 / 33KB) | SyncPage/index + SyncStatusPanel + SyncBundleConfig + SyncHistory | `frontend/src/components/sync/` |
| 2 | [SettingsPanel.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/SettingsPanel.tsx) (713 行 / 30KB) | SettingsPanel/index + ThemeSettings + RefreshSettings + DisplaySettings | `frontend/src/components/settings/` |
| 3 | [FavoritesPanel.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/FavoritesPanel.tsx) (402 行 / 16KB) | FavoritesPanel/index + FavoriteList + FavoriteItem + FavoriteToolbar | `frontend/src/components/favorites/` |
| 4 | [codegarden/ServiceMesh.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/codegarden/ServiceMesh.tsx) (411 行 / 17KB) | ServiceMesh/index + ServiceCard + ServiceDetail + ServiceFilters | `frontend/src/components/codegarden/service-mesh/` |
| 5 | [codegarden/DependencyGraph.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/codegarden/DependencyGraph.tsx) (321 行 / 16KB) | DependencyGraph/index + GraphNode + GraphEdge + ImpactPanel | `frontend/src/components/codegarden/dependency-graph/` |
| 6 | [codegarden/ResourceHub.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/codegarden/ResourceHub.tsx) (389 行 / 15KB) | ResourceHub/index + PortPool + EnvTemplateList + VolumeManager | `frontend/src/components/codegarden/resource-hub/` |

## 3. Out of Scope（明确不做）

- ❌ **不改业务逻辑**：拆分仅是物理切分，props/API 完全保留
- ❌ **不改测试**：现有 .test.tsx 仍跑原文件，Phase 6 才扩展
- ❌ **不做 token 化**：颜色硬编码保留原样（Phase 2-5 才动）
- ❌ **不拆 4KB 以下的文件**：仅拆 6 个明确列出的大文件
- ❌ **不动 App.tsx 路由**（已 Phase 1A 完成）
- ❌ **不引入新依赖**

## 4. 拆分原则（必须遵守）

1. **单文件 ≤ 10KB 且 ≤ 300 行**（`wc -l` 验证）
2. **目录 + index.tsx 模式**：当形成"1 主 + N 子"时启用，导出 index 给外部 import
3. **子组件 props-only**：禁止子组件 import 全局 state / context（除明确声明的 callback）
4. **共享类型抽 `types/`**（仅当 2+ 子组件用同一类型时）
5. **同目录可相对 import**：跨目录用 `@/components/...` 别名
6. **Hook 也可拆**：复杂状态机抽 `useXxx.ts` 放到同目录
7. **保留原导出 API**：SyncPage 等的 prop interface 不变

## 5. 执行步骤（goal 模式按此推进）

### Step 1: SyncPage 拆分（最复杂，先做）

1. `Read frontend/src/components/SyncPage.tsx` 全文（862 行）
2. 用 grep / 注释识别 4 个内聚段：
   - 同步状态展示（连接/拉/推/最近一次时间）
   - 同步包配置（WebDAV / 路径 / master_key / 加密开关）
   - 同步历史列表（最近 N 次 push/pull 记录）
   - 主体页骨架（Header + Tabs + 各段）
3. 抽子组件：
   - `frontend/src/components/sync/index.tsx` — 主体（原 SyncPage 函数体重写为薄壳）
   - `frontend/src/components/sync/SyncStatusPanel.tsx` — 状态面板
   - `frontend/src/components/sync/SyncBundleConfig.tsx` — 同步包配置
   - `frontend/src/components/sync/SyncHistory.tsx` — 历史列表
4. 必要时抽 `frontend/src/components/sync/useSyncBundle.ts` hook
5. 验证：`cd frontend && npx tsc --noEmit && npx vitest run`

### Step 2-6: 重复 Step 1 流程

- Step 2: SettingsPanel（4 子文件 + 1 index）
- Step 3: FavoritesPanel（4 子文件 + 1 index）
- Step 4: codegarden/ServiceMesh（4 子文件 + 1 index）
- Step 5: codegarden/DependencyGraph（4 子文件 + 1 index）
- Step 6: codegarden/ResourceHub（4 子文件 + 1 index）

每个 Step 结束后跑一次 tsc + vitest 验证。

## 6. 验证清单（DoD）

```bash
# 1. 6 大文件已消失
find frontend/src -name "SyncPage.tsx" -o -name "SettingsPanel.tsx" -o -name "FavoritesPanel.tsx" | wc -l
# 期望: 0

# 2. 子文件大小合规
find frontend/src/components/sync frontend/src/components/settings frontend/src/components/favorites frontend/src/components/codegarden/service-mesh frontend/src/components/codegarden/dependency-graph frontend/src/components/codegarden/resource-hub -name "*.tsx" -size +10k | wc -l
# 期望: 0

# 3. 类型 + 测试
cd frontend && npx tsc --noEmit     # 期望: 0 errors
cd frontend && npx vitest run        # 期望: 75+ PASS（数量不变）

# 4. App.tsx import 路径正确
grep -E "from.*SyncPage|SettingsPanel|FavoritesPanel|ServiceMesh|DependencyGraph|ResourceHub" frontend/src/App.tsx
# 期望: 仍能找到（因 index.tsx 转发）
```

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 拆分引入 import 循环 | 拆分前先画依赖图，子组件仅向上 import；共享类型抽 `types/` |
| props 改坏导致业务异常 | 保持 prop interface 与原文件完全一致；tsc 是最后一道防线 |
| 现有 .test.tsx 失败 | 检查测试是否引用内部函数名；如失败，**评估是测试期望过期还是拆分错误**（Rule 7） |
| 路径迁移后 vite cache 异常 | 拆分完成后 `rm -rf frontend/node_modules/.vite` 一次 |

## 8. 决策日志

| 决策 | 选定 | 理由 |
|---|---|---|
| 目录 vs 平铺 | 目录+index | 拆分产生 4 个子文件，目录聚合更清晰 |
| Hook 抽离 | 仅当 ≥80 行时抽 | 避免过度抽象（Rule 2） |
| Props vs Context | 仅 Props | 拆分不引入新耦合 |
| .test.tsx 保留 | 全部保留 | Phase 6 才扩展测试 |

## 9. 完成后

- 提交 commit: `refactor(frontend): split 6 large files into subcomponents`
- 触发 Phase 2 PRD
- 更新 master PRD §4.1 状态为 ✅
