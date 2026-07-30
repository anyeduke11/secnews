# Phase 5 子 PRD — 系统/工具页 + 45 组件最小改动

> **Master PRD**: [UIUX_REFACTOR_PRD.md](file:///Users/duke/Documents/hotspot/docs/UIUX_REFACTOR_PRD.md) v1.0 §4.5 + §4.6
> **前置依赖**: Phase 1A ✅ + Phase 2-4（业务组件完成）
> **预计 commit**: `refactor(frontend): system pages + remaining 45 components token migration (Phase 5)`

---

## 0. Goal (一句话)

3 个系统/工具页（HealthDashboard / HistoryPage / TodosPage）完整改造 + 45 个剩余组件最小改动（仅替换硬编码颜色），累计 ≤ 50 行 diff/文件，达到 100% token 覆盖率。

## 1. 入口 / 出口

- **入口**: Phase 2-4 业务组件完成
- **出口**: 3 系统页完整改造 + 45 组件全部走 token、0 硬编码颜色

## 2. In Scope（必须做）

### 2.1 3 系统/工具页（完整改造）

| # | 组件 | 文件 | 改造重点 |
|---|---|---|---|
| 1 | HealthDashboard | [HealthDashboard.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/HealthDashboard.tsx) (2.1KB) | 状态色（success/warning/error）应用 + EmptyState |
| 2 | HistoryPage | [HistoryPage.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/HistoryPage.tsx) (15KB) | EmptyState 接入 + onBack 移除 + 列表 token 化 |
| 3 | TodosPage | [TodosPage.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/TodosPage.tsx) (14KB) | onBack → useGoHome + Toast 接入 + token 化 |

### 2.2 45 组件最小改动

仅替换硬编码颜色 → token，不动业务逻辑、不动 props、不动 state。

**优先序**（高频可见 > 工具型 > 一次性页面）:

| 优先级 | 组件 | 文件 |
|---|---|---|
| 高 | Header | [Header.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/Header.tsx) |
| 高 | CategoryNav | [CategoryNav.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/CategoryNav.tsx) |
| 高 | StatsPanel | [StatsPanel.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/StatsPanel.tsx) |
| 高 | ItemDetailDialog | [ItemDetailDialog.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/ItemDetailDialog.tsx) |
| 中 | SkillCard / SkillsPage | [SkillsPage.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/SkillsPage.tsx) |
| 中 | SecretList 等 SecretsPage 子组件 | [SecretsPage.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/SecretsPage.tsx) |
| 中 | TodoItem | [TodoItem.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/TodoItem.tsx) |
| 低 | AddTodoForm / TaskSubmitDialog 等 | — |
| 低 | ConceptDetailDialog / PublishDialog | — |
| 低 | RegionFilter / TopBar / Sidebar | — |

完整 45 组件列表见 `docs/UIUX_REMAINING_45.md`（本 phase 启动时生成）。

## 3. Out of Scope（明确不做）

- ❌ **不拆 HistoryPage 15KB / TodosPage 14KB**（业务密集，拆分需重写状态机，超出 token 化范围）
- ❌ **不改 SecretsPage 28KB 业务逻辑**（仅替换可见的硬编码颜色）
- ❌ **不写新测试**（Phase 6 才统一补）
- ❌ **不重写 Header 布局**（仅改颜色）
- ❌ **不引入新依赖**

## 4. 改造规则

### 4.1 onBack 移除规则（仅 HistoryPage / TodosPage）

```tsx
// 改前
export function TodosPage({ onBack }: { onBack: () => void }) {
  return <button onClick={onBack}>返回</button>;
}

// 改后
import { useGoHome } from '@/hooks/useGoHome';
export function TodosPage() {
  const goHome = useGoHome();
  return <button onClick={goHome}>返回</button>;
}
```

App.tsx 同步移除 onBack prop 传递：
```tsx
<Route path="/todos" element={<TodosPage />} />
```

### 4.2 Toast 接入（仅 TodosPage / SecretsPage 关键操作）

```tsx
import { useToast } from './Toast';
const toast = useToast();

const handleSave = async () => {
  try {
    await save();
    toast.show({ type: 'success', message: '已保存' });
  } catch (e) {
    toast.show({ type: 'error', message: e.message, action: { label: '重试', onClick: handleSave } });
  }
};
```

### 4.3 45 组件最小改动规则

每文件 diff 必须 ≤ 50 行：
- 仅替换 `color: '#xxx'` → `var(--xxx)` 或 Tailwind 类名
- 不重构、不重命名、不合并
- 提交时按"按文件多次小 commit"或"批量大 commit"由 agent 决策
- 若某文件改动 > 50 行，**说明该文件应纳入 Phase 1B 拆分**

## 5. 执行步骤

### Step 1: 生成 45 组件清单

```bash
cd /Users/duke/Documents/hotspot
ls frontend/src/components/*.tsx | wc -l
# 当前: ~57 个 .tsx
# 排除 Phase 1A/1B/2/3/4 已改: ~12 个
# 待改: ~45 个
```

输出清单到 `docs/UIUX_REMAINING_45.md`。

### Step 2: HealthDashboard（最简单，先做）

1. 状态色（success/warning/error）替换硬编码
2. EmptyState 接入
3. Loading 态

### Step 3: HistoryPage

1. 替换硬编码颜色
2. EmptyState 接入
3. onBack 移除（App.tsx 同步）
4. 列表分页 token 化

### Step 4: TodosPage

1. 替换硬编码颜色
2. onBack 移除（App.tsx 同步）
3. Toast 接入关键操作
4. EmptyState 接入

### Step 5: 45 组件批量改动

按"高频优先"顺序，每文件：
1. `Read <file>`
2. grep 硬编码颜色
3. 替换（仅颜色，≤ 50 行 diff）
4. tsc 验证

每 10 个文件跑一次 `npx vitest run` 防止累积错误。

### Step 6: 浏览器验证

1. 切换暗/亮主题，所有页无颜色断裂
2. TodosPage 触发增/删/改，验证 Toast 显示
3. HistoryPage 触发空数据（清空 localStorage），验证 EmptyState

## 6. 验证清单（DoD）

```bash
# 1. 全项目 0 硬编码颜色（除注释和 SVG 内嵌）
grep -rE "#[0-9a-fA-F]{3,8}" frontend/src --include="*.tsx" --include="*.ts" --include="*.css" | grep -v "^\s*//" | wc -l
# 期望: 0

# 2. onBack prop 已移除
grep -E "onBack" frontend/src/App.tsx
# 期望: 仅 useGoHome 内部使用

# 3. 类型 + 测试
cd frontend && npx tsc --noEmit
cd frontend && npx vitest run

# 4. 45 组件已改动（diff 统计）
git diff --stat HEAD~1..HEAD -- frontend/src/components/ | tail -50
# 期望: ≥ 45 files changed
```

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 45 组件批量改动引入 import 循环 | 每 10 文件一组验证 tsc |
| 某文件改动 > 50 行 | 标记为 Phase 1B 候选，本 phase 拆分 |
| Toast 接入影响其他组件 | 仅在 TodosPage / SecretsPage 关键操作接 |
| onBack 移除破坏 12 page 中其他 9 个 | Phase 5 仅改 History/Todos，剩余 9 个继续传 onBack 兜底（向后兼容） |

## 8. 决策日志

| 决策 | 选定 | 理由 |
|---|---|---|
| 45 组件最小改动 vs 完整改造 | 最小改动 | Rule 2 简单胜过复杂 |
| onBack 移除范围 | 仅 History/Todos | 减少回归风险 |
| Toast 接入范围 | 仅关键操作 | 避免噪音 |
| HistoryPage/TodosPage 拆分 | 不在 Phase 5 | 业务密集，超出 token 化范围 |

## 9. 完成后

- 提交 commit(s): `refactor(frontend): system pages + 45 components token migration (Phase 5)`（可拆 2-3 个 commit）
- 触发 Phase 6 PRD
- 更新 master PRD §4.5 / §4.6 状态为 ✅
