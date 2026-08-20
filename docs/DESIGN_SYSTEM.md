# hotspot Design System (v1.0)

> 三层架构 (data / judge / action) 统一设计契约
> 维护者: AI + 安全从业者单人工作站

## 1. Design Tokens

所有视觉值通过 CSS variables 定义于 [index.css](file:///Users/duke/Documents/hotspot/frontend/src/index.css)，映射到 Tailwind tokens ([tailwind.config.js](file:///Users/duke/Documents/hotspot/frontend/tailwind.config.js))。

### 色板（dark/light 双主题）

| Token | Dark | Light | 用途 |
|-------|------|-------|------|
| `--bg-primary` | #0a0e14 | #f8fafc | 页面背景 |
| `--bg-elevated` | #141921 | #ffffff | 卡片/容器 |
| `--bg-secondary` | #1a2029 | #f1f5f9 | 表头/输入框 |
| `--bg-hover` | #1f2630 | #e2e8f0 | hover 态 |
| `--border-color` | #2a3340 | #cbd5e1 | 默认边框 |
| `--text-primary` | #e6edf3 | #0f172a | 主文字 |
| `--text-secondary` | #9aa5b1 | #475569 | 次文字 |
| `--text-muted` | #6b7280 | #94a3b8 | 弱文字 |
| `--accent` | #3b82f6 | #2563eb | 强调色（单一） |

**约束**：整个系统只有一个 accent color。不允许多个强调色并存。

### 间距

| Token | 值 | 用途 |
|-------|----|------|
| `--radius-sm` | 4px | 按钮/输入框/小元素 |
| `--radius-md` | 8px | 卡片/容器/表格 |
| `--radius-full` | 9999px | Badge/圆点 |

### 字体

- **Sans**: `Inter, system-ui, -apple-system, sans-serif` — 正文
- **Mono**: `JetBrains Mono, monospace` — 数字/代码/标签

## 2. 组件清单

### 框（Card）
- [LayerCard](file:///Users/duke/Documents/hotspot/frontend/src/components/layout/LayerCard.tsx) — 统一卡片容器
  - 5 变体: `default` / `compact` / `highlight` / `ghost` / `pipeline`
  - 配套: `LayerCardRow` / `LayerCardGrid` / `LayerEmptyState` / `LayerSkeleton`
- **禁止**：不再允许 `bg-white dark:bg-gray-800 rounded-lg shadow` 这类散落样式

### 表（Table）
- [LayerTable](file:///Users/duke/Documents/hotspot/frontend/src/components/layout/LayerTable.tsx) — 统一表格
  - 斑马纹可选 (`zebra`)
  - 紧凑模式 (`compact`)
  - loading/empty 状态内置

### 按钮（Button）
- CSS 类（[index.css:L585-665](file:///Users/duke/Documents/hotspot/frontend/src/index.css#L585-L665)）
  - `btn-primary` — 主操作（实色背景）
  - `btn-accent` — 次强调（描边）
  - `btn-ghost` — 透明幽灵
  - `btn-secondary` — 中性次按钮
- 所有按钮都有 hover/active/disabled/focus-visible 状态

### 徽标（Badge）
- [LayerBadge](file:///Users/duke/Documents/hotspot/frontend/src/components/layout/LayerBadge.tsx)
  - 3 变体: `solid` / `soft` / `outline`
- 历史的 `.editorial-badge` CSS 类继续可用（已与 LayerBadge 对齐）

### 图标（Icon）
- [Icon.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/Icon.tsx) — 统一封装
  - 规格: 14×14 / `currentColor` / `strokeWidth="2"` / 圆角线帽
  - `aria-hidden="true"` (装饰性)

## 3. 布局

- **容器**: `max-width: 1320px` + `mx-auto` + `px-4 sm:px-8 lg:px-10`
- **三层路由**: `/data` (资料) → `/judge` (判断) → `/action` (行动)
- **PageLayout**: [PageLayout.tsx](file:///Users/duke/Documents/hotspot/frontend/src/components/PageLayout.tsx)
  - 含 skip-link (a11y)
  - `min-h-[100dvh]` (非 100vh)

## 4. 交互状态

| 状态 | 实现 |
|------|------|
| hover | `var(--bg-hover)` |
| active | `transform: scale(0.97)` |
| focus-visible | `outline: 2px solid var(--accent)` + `outline-offset: 2px` |
| disabled | `opacity: 0.35` + `pointer-events: none` |
| loading | `LayerSkeleton` (骨架屏) |
| empty | `LayerEmptyState` |
| error | inline message (非 alert) |

## 5. 无障碍 (a11y)

- **focus-ring**: 34 个文件已使用 `.focus-ring` 类
- **skip-link**: PageLayout 含跳转到主内容
- **aria-label**: 所有图标按钮必须有 `aria-label`
- **键盘导航**: Tab 顺序 = 视觉顺序; focus 可见
- **颜色对比度**: dark/light 都 ≥ 4.5:1 (WCAG AA)

## 6. Onboarding

- [OnboardingHint](file:///Users/duke/Documents/hotspot/frontend/src/components/layout/OnboardingHint.tsx)
- localStorage 记忆已读状态
- 6 认知模式首次访问时显示一次

## 7. 禁止清单

- 硬编码颜色 (`#hex`) — 必须用 `var(--*)`
- 硬编码间距 (`padding: 12px`) — 必须用 Tailwind 类或 token
- `bg-white dark:bg-gray-800` — 必须用 `LayerCard` 或 `var(--bg-elevated)`
- 自建 `<table>` — 必须用 `LayerTable`
- `window.alert()` — 必须用 `Toast` 或 inline error
- `100vh` — 必须用 `100dvh`
