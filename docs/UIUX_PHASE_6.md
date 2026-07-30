# Phase 6 子 PRD — 15 个测试补强

> **Master PRD**: [UIUX_REFACTOR_PRD.md](file:///Users/duke/Documents/hotspot/docs/UIUX_REFACTOR_PRD.md) v1.0 §5
> **前置依赖**: Phase 1A-5 完成
> **预计 commit**: `test(frontend): add 15 high-frequency component tests (Phase 6)`

---

## 0. Goal (一句话)

为 Phase 1A 原子组件（4 个）、Phase 1B 拆分子组件（6 个）、Phase 2-4 高频组件（5 个）补 15 个 .test.tsx，覆盖率从 75+ 提升到 90+，确保拆分与 token 化无回归。

## 1. 入口 / 出口

- **入口**: Phase 1B-5 完成（拆分 + token 化）
- **出口**: 15 个 .test.tsx 全部 PASS，vitest 90+ 用例

## 2. In Scope（必须做）

### 2.1 Phase 1A 原子组件（4 个，新建）

| # | 组件 | 测试重点 |
|---|---|---|
| 1 | EmptyState | render + 4 变体（带 icon / 带 action / compact / 默认） |
| 2 | ErrorBoundary | throw 触发 fallback + onReset 恢复 |
| 3 | Toast | useToast().show/dismiss + 4 类型 + 自动消失 |
| 4 | PageLayout | render Outlet + ToastProvider 注入 |

### 2.2 Phase 1B 拆分子组件（6 个，新建或扩展）

| # | 子组件 | 位置 | 测试重点 |
|---|---|---|---|
| 5 | SyncStatusPanel | `sync/SyncStatusPanel.tsx` | render 4 状态（idle/pulling/pushing/error） |
| 6 | SettingsPanel 子组件 | `settings/ThemeSettings.tsx` 等 | render + 切换主题 |
| 7 | FavoritesPanel 子组件 | `favorites/FavoriteList.tsx` | render + toggle |
| 8 | ServiceCard | `service-mesh/ServiceCard.tsx` | render + restart 点击 |
| 9 | GraphNode | `dependency-graph/GraphNode.tsx` | render + click |
| 10 | PortPool | `resource-hub/PortPool.tsx` | render + allocate |

### 2.3 Phase 2-4 高频组件（5 个，新建或扩展）

| # | 组件 | 测试重点 |
|---|---|---|
| 11 | HotspotCard | render + 收藏切换（已存在则扩展） |
| 12 | HotspotGrid | Empty/Loading 状态 |
| 13 | TrendChart | 暗/亮主题切换（mock useTheme） |
| 14 | KnowledgeGraph | 节点 + 边 render |
| 15 | MasteryGauge | 3 分数段颜色 |

## 3. Out of Scope（明确不做）

- ❌ **不补 45 组件测试**（仅最高频 15 个）
- ❌ **不改现有失败的测试**（若现有 .test.tsx 失败，先**评估是测试期望过期还是业务 bug**（Rule 7））
- ❌ **不写 e2e 测试**（仅 unit + integration 级别）
- ❌ **不引入 React Testing Library 新 API**（使用已配置的）
- ❌ **不写 snapshot 测试**（Rule 9：测试验证 intent，不验证具体渲染）
- ❌ **不测 hooks 内部**（除 useToast 必须测）

## 4. 测试规则（必须遵守）

### 4.1 测试结构

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Component } from './Component';

describe('Component', () => {
  it('renders required elements', () => {
    render(<Component title="test" />);
    expect(screen.getByText('test')).toBeInTheDocument();
  });

  it('handles user interaction', () => {
    const onAction = vi.fn();
    render(<Component onAction={onAction} />);
    fireEvent.click(screen.getByRole('button'));
    expect(onAction).toHaveBeenCalledTimes(1);
  });
});
```

### 4.2 关键 intent 覆盖

每个测试必须验证**WHY** 而非**WHAT**：
- ❌ `expect(wrapper.find('.btn').length).toBe(1)` — 仅验证存在
- ✅ `expect(onSave).toHaveBeenCalledWith({ name: 'x' })` — 验证业务行为

### 4.3 mock 策略

- ECharts / Recharts: `vi.mock('echarts-for-react', () => ({ default: () => null }))`
- fetch: `vi.spyOn(global, 'fetch').mockResolvedValue(...)`
- useTheme: 渲染时通过 ThemeContext.Provider 注入
- useNavigate: react-router-dom MemoryRouter 包裹

### 4.4 已有 .test.tsx 扩展

- `codegarden/ProjectList.test.tsx`、`codegarden/ProjectCard.test.tsx` 等已存在
- 扩展时**新增 it()** 而非修改现有 it()
- 命名约定: `it('Phase 1B: handles X', ...)`

## 5. 执行步骤

### Step 1: 创建 4 个原子组件测试

1. `frontend/src/components/EmptyState.test.tsx`
2. `frontend/src/components/ErrorBoundary.test.tsx`
3. `frontend/src/components/Toast.test.tsx`
4. `frontend/src/components/PageLayout.test.tsx`

### Step 2: 创建 6 个拆分子组件测试

1. `frontend/src/components/sync/SyncStatusPanel.test.tsx`
2. `frontend/src/components/settings/ThemeSettings.test.tsx`
3. `frontend/src/components/favorites/FavoriteList.test.tsx`
4. `frontend/src/components/codegarden/service-mesh/ServiceCard.test.tsx`
5. `frontend/src/components/codegarden/dependency-graph/GraphNode.test.tsx`
6. `frontend/src/components/codegarden/resource-hub/PortPool.test.tsx`

### Step 3: 扩展 5 个高频组件测试

1. `frontend/src/components/HotspotCard.test.tsx` — 新建
2. `frontend/src/components/HotspotGrid.test.tsx` — 新建
3. `frontend/src/components/TrendChart.test.tsx` — 新建
4. `frontend/src/components/KnowledgeGraph.test.tsx` — 新建
5. `frontend/src/components/MasteryGauge.test.tsx` — 新建

### Step 4: 验证

```bash
cd frontend && npx vitest run
# 期望: 90+ PASS
```

### Step 5: 覆盖率检查（可选）

```bash
cd frontend && npx vitest run --coverage
# 期望: components/ 覆盖率 ≥ 60%
```

## 6. 验证清单（DoD）

```bash
# 1. 15 个 .test.tsx 存在
find frontend/src -name "*.test.tsx" | wc -l
# 期望: ≥ 90（现有 75 + 新增 15）

# 2. vitest 0 失败
cd frontend && npx vitest run
# 期望: Test Files 0 failed, Tests 90+ passed

# 3. tsc 0 错误
cd frontend && npx tsc --noEmit

# 4. 测试覆盖关键 intent（人工抽查 3 个）
# 验证: onAction 被调用、状态切换、空数据/错误分支
```

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 现有 .test.tsx 因拆分失败 | 评估是测试期望过期还是拆分错误（Rule 7） |
| ECharts/Recharts mock 不全 | 使用最简 mock（返回 null）覆盖关键 props 即可 |
| Toast 计时器不可控 | vi.useFakeTimers() 控制时间 |
| 路由组件测试困难 | MemoryRouter + 固定 initialEntries |

## 8. 决策日志

| 决策 | 选定 | 理由 |
|---|---|---|
| 测试数量 | 15 | master PRD §5 锁定 |
| snapshot 测试 | 不写 | Rule 9 反对 |
| 覆盖率门槛 | 60% | 不强求 80%+，优先 intent 覆盖 |
| mock 策略 | 最小化 | 避免 mock 失真 |

## 9. 完成后

- 提交 commit: `test(frontend): add 15 high-frequency component tests (Phase 6)`
- 触发 Phase 7 PRD
- 更新 master PRD §5 状态为 ✅
