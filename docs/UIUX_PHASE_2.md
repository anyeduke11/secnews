# Phase 2 子 PRD — SecNews 热点聚合改造

> **Master PRD**: [UIUX_REFACTOR_PRD.md](file:///Users/duke/Documents/hotspot/docs/UIUX_REFACTOR_PRD.md) v1.0 §4.2
> **前置依赖**: Phase 1A ✅ + Phase 1B（若 1B 未做，本 phase 也可独立做，但会增大单文件 diff）
> **预计 commit**: `refactor(frontend): secnews hotspot UI token migration (Phase 2)`

---

## 0. Goal (一句话)

SecNews 热点聚合 4 个核心组件 100% 走 token 系统：硬编码 `#xxx` 颜色清零、EmptyState/LoadingSkeleton 状态接入、暗/亮双主题无视觉回归。

## 1. 入口 / 出口

- **入口**: Phase 1A 交付（token 完整 + 原子组件就绪）
- **出口**: HotspotCard / HotspotGrid / TrendChart / SearchBar 4 个组件 0 硬编码颜色、4 状态统一组件、暗/亮双主题 0 闪烁

## 2. In Scope（必须做）

| # | 组件 | 文件 | 改造重点 |
|---|---|---|---|
| 1 | HotspotCard | [HotspotCard.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/HotspotCard.tsx) (6.5KB) | 6 分类色 token 化 + hover/active 统一 |
| 2 | HotspotGrid | [HotspotGrid.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/HotspotGrid.tsx) (7.7KB) | Loading/Empty/Error 三态 + 分页 token 化 |
| 3 | TrendChart | [TrendChart.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/TrendChart.tsx) (4.2KB) | ECharts 暗/亮主题切换（颜色引用 token） |
| 4 | SearchBar | [SearchBar.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/SearchBar.tsx) (3.8KB) | focus-ring / 暗/亮 input 样式统一 |

## 3. Out of Scope（明确不做）

- ❌ **不拆文件**：Phase 1B 已拆/本 phase 假设 4 个文件均 < 10KB
- ❌ **不改业务逻辑**（props / state / fetch 全部保留）
- ❌ **不重写测试**（除非现有测试因 token 化失败）
- ❌ **不动 Header / CategoryNav / StatsPanel**（这些算 §4.6 的 45 组件最小改动范围，Phase 5 做）
- ❌ **不引入 ECharts 新配置**：仅替换颜色为 token 引用

## 4. 改造规则（必须遵守）

### 4.1 颜色 token 化规则

```tsx
// ❌ 改前
<div style={{ color: '#e85d5d' }} />
<div className="text-[#e85d5d]" />

// ✅ 改后
<div className="text-security" />              // Tailwind 语义类
<div style={{ color: 'var(--color-security)' }} /> // CSS 变量
```

**可用的 Tailwind 类名**（来自 Phase 1A 配置）:
- 分类色: `text-cat-ai` / `bg-cat-security` / `border-cat-finance` 等
- 状态色: `text-success` / `text-warning` / `text-error` / `text-info`
- 表面色: `bg-dark-bg` / `bg-dark-card` / `bg-dark-hover` / `bg-dark-elevated` / `border-dark-border`
- 文字: `text-text-main` / `text-text-secondary` / `text-text-muted`

### 4.2 状态接入规则

| 状态 | 使用组件 |
|---|---|
| 加载中 | `<LoadingSkeleton />` 或组件内 `<div className="animate-shimmer" />` |
| 空数据 | `<EmptyState title="..." description="..." actionLabel="..." onAction={...} />` |
| 错误 | `<EmptyState icon={<Icon>...</Icon>} title="加载失败" description={error.message} actionLabel="重试" onAction={refresh} />` |
| 成功 | 正常渲染 |

### 4.3 ECharts 暗/亮主题规则

- 读取 `document.documentElement.getAttribute('data-theme')`
- useEffect 监听 theme 变化，setOption 重新应用 colors
- 颜色数组从 `var(--color-*)` 通过 `getComputedStyle()` 读取
- 或维护 `DARK_COLORS` / `LIGHT_COLORS` 两个常量，theme 切换时替换

## 5. 执行步骤（goal 模式按此推进）

### Step 1: HotspotCard（最高频，先做）

1. `Read frontend/src/components/HotspotCard.tsx`
2. grep `#[0-9a-fA-F]{3,8}` 找硬编码颜色
3. 替换为 Tailwind 语义类 / `var(--*)`
4. 检查 hover/active 状态是否走 `card-base` className
5. 验证：`npx tsc --noEmit`

### Step 2: HotspotGrid

1. 替换硬编码颜色
2. Loading 态用 `<LoadingSkeleton />`
3. Empty 态用 `<EmptyState title="暂无热点" description="5 分钟自动刷新" actionLabel="立即刷新" onAction={refresh} />`
4. Error 态用 `<EmptyState>` + error icon
5. 分页按钮 hover/disabled 态用 token

### Step 3: TrendChart

1. 引入 `useTheme()` hook
2. 抽出 `getChartColors(theme)` 函数，返回 ECharts series colors 数组
3. useEffect 监听 theme 变化，setOption 更新
4. tooltip 背景色用 `var(--bg-elevated)`、文字色用 `var(--text-primary)`

### Step 4: SearchBar

1. input 背景 `var(--bg-card)`、边框 `var(--border-color)`、focus 边框 `var(--color-ai)`
2. 添加 `focus-ring` className
3. placeholder 颜色 `var(--text-muted)`
4. time range 按钮组用统一 button 样式

### Step 5: 浏览器手动验证

1. 启动 dev server: `cd frontend && npm run dev`
2. 切换暗/亮主题，确认 4 组件无颜色断裂 / 无残留硬编码
3. 触发空数据场景（mock 空响应），确认 EmptyState 渲染
4. 检查控制台 0 warning（除已知 react-router 警告）

## 6. 验证清单（DoD）

```bash
# 1. 4 文件 0 硬编码颜色
grep -E "#[0-9a-fA-F]{3,8}" frontend/src/components/HotspotCard.tsx frontend/src/components/HotspotGrid.tsx frontend/src/components/TrendChart.tsx frontend/src/components/SearchBar.tsx | grep -v "^\s*//" | wc -l
# 期望: 0

# 2. 类型 + 测试
cd frontend && npx tsc --noEmit     # 期望: 0 errors
cd frontend && npx vitest run        # 期望: 75+ PASS

# 3. 状态组件使用情况
grep -l "EmptyState\|LoadingSkeleton" frontend/src/components/Hotspot*.tsx
# 期望: 至少 HotspotGrid.tsx
```

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| ECharts 主题切换闪烁 | setOption 时合并 oldOption，避免重新 init |
| var(--xxx) 在 ECharts 不识别 | 通过 getComputedStyle 读取具体 RGB 字符串传入 ECharts |
| 替换颜色后 hover 态失效 | 用 `card-base:hover` 而非独立 hover className |
| Tailwind 动态类名不被识别 | 用完整字符串字面量，不用模板拼接 |

## 8. 决策日志

| 决策 | 选定 | 理由 |
|---|---|---|
| 颜色表达方式 | 优先 Tailwind 语义类 | 与 Phase 1A 配置一致 |
| ECharts 颜色传递 | getComputedStyle 转 RGB | ECharts 不识别 CSS 变量 |
| EmptyState 文案 | 简短，附引导 action | 提升可用性 |
| Hover 动画 | 沿用 card-base | 不引入新动画 |

## 9. 完成后

- 提交 commit: `refactor(frontend): secnews hotspot UI token migration (Phase 2)`
- 触发 Phase 3 PRD
- 更新 master PRD §4.2 状态为 ✅
