# Hotspot 视觉与交互设计规范 v4.0

> 项目: `/Users/duke/Documents/hotspot`
> 适用版本: 站点所有页面
> 制定日期: 2026-07-06
> 状态: 实施中

---

## 0. 设计读数 (Design Read)

**Reading this as:** 数据门户 / 监控仪表,目标读者是科技/安全/金融从业者;语言为 **"Bloomberg 终端 × Linear"** 的等宽气质;倾向 **深色 + 浅色双模的高密度数据 UI**,以 6 类色码做语义锚点。

### 0.1 三档配置

| 档位 | 值 | 推导 |
|------|----|------|
| `DESIGN_VARIANCE` | 6 | 数据门户型需要网格纪律,允许 2-3 处偏置即可,不做艺术化 |
| `MOTION_INTENSITY` | 4 | 用户要求"流畅"但避免影视化,纯 CSS 过渡 + 节制入场 |
| `VISUAL_DENSITY` | 5 | 用户原话"紧凑",偏数据密度高 |

### 0.2 核心原则

1. **数据第一,装饰次之。** 任何新视觉元素都要回答"它让用户更易找到信息了吗?"。否则不加。
2. **6 类色是语义系统,不是装饰。** 每类色对应一个 Category;UI 中的 dot / bar / chart 颜色都来自 `--color-{cat}` token,不写死 hex。
3. **等宽优先。** 数字、时间、版本号、坐标全部用 `font-mono` + `tabular-nums`,保证对齐。
4. **同主题锁定。** 同一页面 / 同一屏不混深浅。
5. **降级路径显式。** `prefers-reduced-motion: reduce` 时所有动画时长降到 0.01ms。

---

## 1. 品牌资产 (不可改)

### 1.1 类别色板 (Category Palette)

| Token | 类别 | Hex | 对比度 vs bg-primary |
|-------|------|-----|---------------------|
| `--color-ai` | 科技 / AI | `#00bcd4` | 4.6:1 (WCAG AA pass) |
| `--color-security` | 网络安全 | `#e85d5d` | 4.5:1 |
| `--color-finance` | 金融 / 投资 | `#f0c929` | 3.0:1 (仅作大字 / icon,不作正文) |
| `--color-startup` | 独立开发 / 创业 | `#7c6aff` | 4.6:1 |
| `--color-bid` | 招标资讯 | `#e8891a` | 3.4:1 (大字 / icon 用) |
| `--color-github` | GitHub 项目 | `#8b5cf6` | 4.5:1 |
| `--color-general` | 通用 / 健康 | `#00c96a` | 4.9:1 |

**派生色 (8% / 20% / 50% 透明叠加)** 用于 hover/active/highlight 背景,不出现在调色板本体。

### 1.2 等宽字栈 (Monospace Stack)

```
font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'SF Mono', Menlo, monospace;
```

正文中文回退到系统中文栈:

```css
font-family: 'JetBrains Mono', -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;
```

**不引入** Inter / Roboto / Open Sans 等比例西文字体,避免破坏等宽气质。

---

## 2. 设计令牌 (Design Tokens)

### 2.1 颜色 (Color)

#### 深色模式 (default)

```css
--bg-primary:    #0a0a0f;  /* 页面底色,非纯黑 */
--bg-card:       #111118;  /* 卡片 */
--bg-elevated:   #1c1c2e;  /* 弹层、菜单 */
--bg-hover:      #181825;  /* hover 状态 */
--border-color:  #1e1e30;  /* 1px 分隔 */
--border-strong: #2a2a40;  /* 强分隔 (header bottom) */
--border-subtle: rgba(255,255,255,0.04);

--text-primary:   #e8e8ee;  /* 4.5:1 vs bg-primary */
--text-secondary: #8888a0;  /* 3.5:1 (副文) */
--text-muted:     #555568;  /* 2.5:1 (仅占位/时间戳) */

--shadow-card:     0 1px 3px rgba(0,0,0,0.3), 0 1px 2px rgba(0,0,0,0.2);
--shadow-elevated: 0 8px 24px rgba(0,0,0,0.5), 0 2px 4px rgba(0,0,0,0.3);
--shadow-glow-ai:  0 0 0 1px rgba(0,188,212,0.3), 0 0 12px rgba(0,188,212,0.1);
```

#### 浅色模式

```css
--bg-primary:    #f4f4f8;
--bg-card:       #ffffff;
--bg-elevated:   #ffffff;
--bg-hover:      #eeeef4;
--border-color:  #dcdce6;
--border-strong: #c4c4d0;
--border-subtle: rgba(0,0,0,0.04);

--text-primary:   #1a1a2e;
--text-secondary: #555570;
--text-muted:     #9999aa;

--shadow-card:     0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.03);
--shadow-elevated: 0 8px 24px rgba(0,0,0,0.08), 0 2px 4px rgba(0,0,0,0.04);
--shadow-glow-ai:  0 0 0 1px rgba(0,188,212,0.4), 0 0 12px rgba(0,188,212,0.15);
```

### 2.2 排版 (Typography)

| Token | Size / Line | 用途 |
|-------|-------------|------|
| `text-display` | 32/40 px, `font-weight: 700`, `letter-spacing: -0.02em` | 落地页 H1 |
| `text-h1` | 24/32 px, `font-weight: 700`, `letter-spacing: -0.015em` | 页面标题 |
| `text-h2` | 18/26 px, `font-weight: 600` | 区块标题 |
| `text-h3` | 14/22 px, `font-weight: 600` | 卡片标题 |
| `text-body` | 13/20 px, `font-weight: 400` | 正文 |
| `text-small` | 12/18 px | 副文 |
| `text-caption` | 11/16 px | 标签、时间戳 |
| `text-overline` | 10/14 px, `font-weight: 600`, `letter-spacing: 0.08em`, `text-transform: uppercase` | 区块小标题(eyebrow) |
| `text-mono-num` | 同 caption, `font-family: mono`, `font-variant-numeric: tabular-nums` | 所有数字 |

> 关键规则: 数字、时间、版本号强制 `font-mono` + `tabular-nums`,避免等宽字段错位。

### 2.3 间距 (Spacing Scale)

8 点网格,紧凑模式使用 4 点子间距:

```
0   0.5  1    1.5  2    2.5  3    3.5  4    5    6    8    10   12   16
0   2px  4px  6px  8px  10px 12px 14px 16px 20px 24px 32px 40px 48px 64px
```

**容器**:
- 页面 max-width: `1280px` (从原 7xl)
- 侧边内边距: `px-4` (mobile) → `px-6` (≥md) → `px-8` (≥lg)
- 区块纵向间距: `py-5` (mobile) → `py-6` (≥md)
- 卡片内边距: `p-3.5` (紧凑) / `p-4` (默认) / `p-5` (宽松)

### 2.4 圆角 (Radius)

**单档系统** (锁住一致性):

| Token | 值 | 用途 |
|-------|----|------|
| `--radius-xs` | 4px | 标签、徽章内圆角 |
| `--radius-sm` | 6px | 按钮、input |
| `--radius-md` | 10px | **卡片默认** |
| `--radius-lg` | 14px | 弹层、大卡片 |
| `--radius-full` | 9999px | 圆点 / 头像 / pill |

> 圆角档位 **不可混用** - 同一组件树内只用一档;按钮圆角 = 卡片圆角 - 2px。

### 2.5 阴影 (Shadow)

| Token | 用途 |
|-------|------|
| `shadow-card` | 默认卡片(微抬升) |
| `shadow-elevated` | hover 状态、弹层 |
| `shadow-glow-ai` | 主品牌色发光,仅用于"重点"按钮 / 焦点态 |

> 浅色模式下阴影带轻微品牌色调 (`rgba(0,188,212,0.06)`),不用纯黑。

### 2.6 动效 (Motion)

| Token | Duration | Easing | 用途 |
|-------|----------|--------|------|
| `--motion-fast` | 120ms | `cubic-bezier(0.16, 1, 0.3, 1)` | hover, color |
| `--motion-base` | 200ms | `cubic-bezier(0.16, 1, 0.3, 1)` | 入场, transform |
| `--motion-slow` | 320ms | `cubic-bezier(0.16, 1, 0.3, 1)` | 列表 stagger |
| `--motion-emphasis` | 480ms | `cubic-bezier(0.16, 1, 0.3, 1)` | 弹层 |

> 全局 `prefers-reduced-motion: reduce` 时,所有 duration 改为 `0.01ms`。

---

## 3. 布局系统 (Layout)

### 3.1 桌面布局 (≥ 1024px)

```
┌──────────────────────────────────────────────────────────────┐
│  Header  [logo] [title]              [status] [actions]      │  64px
├──────────────────────────────────────────────────────────────┤
│  CategoryNav  (pill row, sticky)                              │  44px
├──────────────────────────────────────────────────────────────┤
│  SearchBar  (keyword + time range + sort)                     │  52px
├──────────────────────────────────────────────────────────────┤
│                                                                │
│  StatsPanel  (6 categories, 5-col grid)         [TrendChart]  │  3:1 ratio
│                                                                │
├──────────────────────────────────────────────────────────────┤
│                                                                │
│  HotspotGrid  (1/2/3/4 col responsive)                        │
│  ┌──────┬──────┬──────┬──────┐                                │
│  │ card │ card │ card │ card │                                │
│  └──────┴──────┴──────┴──────┘                                │
│                                                                │
├──────────────────────────────────────────────────────────────┤
│  Pagination                                                    │
├──────────────────────────────────────────────────────────────┤
│  Footer (sources · version)                                   │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 移动端 (< 768px)

```
┌──────────────────────────┐
│  Header  [≡]  [title]    │  56px
│           [status]       │
├──────────────────────────┤
│  CategoryNav (横向滚动)   │  44px
├──────────────────────────┤
│  SearchBar  (折叠)        │  48px
├──────────────────────────┤
│  StatsPanel (2 col)       │
│  TrendChart              │
├──────────────────────────┤
│  HotspotGrid (1 col)     │
├──────────────────────────┤
│  Pagination               │
└──────────────────────────┘
```

### 3.3 栅格 (Grid)

- **主网格**: CSS Grid, `grid-template-columns: repeat(auto-fill, minmax(280px, 1fr))`, gap: 14px (3.5)
- **统计网格**: `grid-cols-2 sm:grid-cols-3 lg:grid-cols-5`, gap: 16px / 12px
- **顶部状态条**: 水平 flex, 间距 8px, 容器 `flex-wrap: wrap`
- **永远不要**用 `w-[calc(33%-1rem)]` 这种 flex 数学,改用 Grid。

### 3.4 容器宽度 (Container)

| 断点 | max-width |
|------|----------|
| `< 640` | `100%` (px-4) |
| `≥ 640` | `640px` |
| `≥ 768` | `768px` |
| `≥ 1024` | `1024px` |
| `≥ 1280` | `1200px` |
| `≥ 1536` | `1280px` |

---

## 4. 组件模式 (Component Patterns)

### 4.1 按钮 (Button)

**3 个变体**:

| 变体 | 用途 | 样式 |
|------|------|------|
| `btn-ghost` | 次要操作 | 1px border + transparent bg + hover 渐入 |
| `btn-primary` | 主要操作 | 实心 brand-ai bg + dark text + glow on hover |
| `btn-icon` | 纯图标 | 28×28 圆角,hover bg-hover |

**统一规则**:
- 高度: 28px (小) / 36px (中) / 44px (大)
- 圆角: `--radius-sm` (6px)
- `:active` 状态: `transform: scale(0.97)` 模拟按压
- 焦点环: `outline: 2px solid var(--color-ai); outline-offset: 2px;` (仅 `:focus-visible`)
- **永远不** 出现 "X" 包裹的 CTAs: 标签 ≤ 8 字符 / 2 词

### 4.2 卡片 (Card)

**两档**:

#### Compact (默认 - HotspotCard)

```
┌────────────────────────────────────────┐
│ ▍[科技/AI]  [Q:90]    2h 前     [☆]   │  28px header
│ 标题标题标题标题标题标题标题标题标题标题  │  2 lines max
│ 摘要摘要摘要摘要摘要摘要摘要摘要摘要…     │  2 lines max
│ ───────────────────────────────────     │  hairline
│ 来源 · 36氪                  阅读 →    │  22px footer
└────────────────────────────────────────┘
```

- 圆角: `var(--radius-md)` (10px)
- 内边距: `p-3.5`
- 左边竖条: `border-left: 2px solid var(--cat-color)` 表达类别
- hover: `transform: translateY(-1px); shadow-elevated`
- :active: `transform: scale(0.99)`

#### Full (StatsPanel / TrendChart)

- 同样 `card-base` + 圆角 10px
- 内边距: `p-4`
- 标题区: 11px overline, uppercase, tracking 0.08em, text-secondary
- 数值区: `font-mono tabular-nums`

### 4.3 类目导航 (CategoryNav)

**视觉**: pill 列表,左对齐,水平 flex-wrap。

| 状态 | 视觉 |
|------|------|
| 默认 | transparent bg + 1px border-color + text-secondary |
| hover | bg-hover + text-primary |
| active | `${color}14` bg + `${color}50` border + brand color text + 数字徽章 |
| 带数据 | 右侧 `tabular-nums` 数字徽章 |

- 字号: 13px
- 圆角: `var(--radius-sm)` (6px)
- 高: 32px
- 间距: gap-1.5 (6px)
- **移除** 每个 pill 前的色点 - 选中的色已经够明显,色点会冗余 (避免 AI Tell: 装饰状态点)

### 4.4 状态条 (Status Strip)

顶部 Header 内,作为 meta 信息:

```
┌─ 实时 · 128 条 │ 更新 14:32:08 │ 距下次刷新 04:23 ─┐
```

- 等宽, `font-mono tabular-nums`
- 颜色: text-muted
- 实时圆点: `pulse-dot` 动画 (2s loop), 颜色 `--color-general`
- 整条用 1px hairline 分隔,**不**用 card 容器

### 4.5 图表 (TrendChart)

- 主题色严格从 `--color-{cat}` 读取,**不**写死 hex
- 网格: `var(--border-subtle)`, 1px, dasharray "3 3"
- 轴线: `var(--border-color)`, 0.5px
- 轴标: 10px, `font-mono`, text-muted
- 柱圆角: `[2, 2, 0, 0]` (顶部圆角)
- 间距: `barCategoryGap: "20%"`, `barGap: 2`
- 堆叠 (`stackId="a"`) 而非分组
- legend 字号 10px,iconSize 7px circle
- tooltip 卡片样式: bg-elevated + 1px border + radius-sm

### 4.6 加载/空态/错误态 (States)

| 状态 | 视觉 |
|------|------|
| 加载 | `LoadingSkeleton`: 与最终布局同形状,shimmer 动画 1.5s |
| 空 | 居中 icon + 标题 + 1 行解释 + 1 个"调整筛选"提示 |
| 错误 | 居中 icon (红色) + 标题 + 错误详情 + 1 个"重试"按钮 |

永远不要只显示白屏 / 圆 spinner。

---

## 5. 交互原型 (Interaction Prototypes)

### 5.1 数据流 (Data flow)

```
用户操作 → CategoryNav 选中 → onChange(cat)
                                ↓
                          useHotspotData 拉 /api/hotspots?category=X
                                ↓
                          LoadingSkeleton 显示 (0.2s 渐入)
                                ↓
                          卡片 stagger 入场 (60ms 间隔, 200ms 一次)
                                ↓
                          滚动到 TrendChart → fetch /api/trends
                                ↓
                          chart 渐入 + bar 上升
```

### 5.2 关键交互时序

#### 卡片 hover (200ms)

```
t=0     : border-color: var(--border-color)
t=0-120 : transition border-color (--motion-fast)
t=0-200 : transition transform (--motion-base)
t=200   : translateY(-1px) + shadow-elevated
```

#### 卡片入场 stagger (320ms 总)

```
卡片 N (N=0..9) 在 t=N*40ms 开始:
  t=0    : opacity 0, translateY(8px)
  t=320  : opacity 1, translateY(0)
```

#### Header 状态条更新 (1s tick)

```
每秒 1 次:
  - 当前时间 HH:MM:SS 写入 `--now`
  - 距下次刷新倒计时减 1
  - 0 时触发 refresh()
```

#### 主题切换 (250ms)

```
document.documentElement.setAttribute('data-theme', X)
body: transition background-color / color (250ms)
所有 .card-base: 跟随 CSS 变量,自动过渡
```

### 5.3 入场动画 (Page-level)

仅作用于:

1. HotspotGrid 卡片列表 (stagger 40ms)
2. TrendChart 容器 (fade + scale 0.98→1, 200ms)
3. StatsPanel 容器 (fade + translateY 8px→0, 200ms)
4. 模态弹层 (fade + scale 0.95→1, 320ms)

**不**作用于: 顶部 Header、CategoryNav、Footer (他们应该"已在那里")。

---

## 6. 响应式适配 (Responsive)

### 6.1 断点

| Token | 最小宽度 | 说明 |
|-------|---------|------|
| `sm` | 640px | 手机横屏 |
| `md` | 768px | 平板 |
| `lg` | 1024px | 笔记本 |
| `xl` | 1280px | 桌面 |
| `2xl` | 1536px | 大屏 |

### 6.2 关键断点行为

| 元素 | `< 640` | `≥ 640` | `≥ 1024` | `≥ 1280` |
|------|---------|---------|----------|----------|
| 容器 | `px-4` | `px-6` | `px-8` | `px-10` |
| Header | 56px, logo + status 折叠 | 64px, 完整 | 64px | 64px |
| CategoryNav | 横向滚动, 隐藏滚动条 | flex-wrap | flex-wrap | flex-wrap |
| HotspotGrid | 1 col | 2 col | 3 col | 4 col |
| StatsPanel | 2 col | 3 col | 5 col | 5 col + TrendChart 同行 |
| TrendChart | 100% 在 StatsPanel 下方 | 100% | 100% | 与 StatsPanel 1:1 并排 |

### 6.3 触屏优化

- 所有可点击元素 ≥ 32×32 px (按钮实际是 28px, 容器加 padding 4px 后 = 32px hit area)
- `touch-action: manipulation` 阻止 300ms 延迟
- `overscroll-behavior: contain` 防止页面级 overscroll

---

## 7. 可访问性 (Accessibility)

### 7.1 颜色对比 (WCAG AA)

| 组合 | 对比度 | 通过 |
|------|--------|------|
| text-primary on bg-primary | 13:1 (dark) / 12:1 (light) | AAA |
| text-secondary on bg-primary | 5.5:1 (dark) / 7:1 (light) | AA |
| text-muted on bg-primary | 3:1 (dark) / 3.5:1 (light) | 仅用于大字号 / 占位 |
| color-ai 文字 on bg-primary | 7.5:1 (dark) / 4.6:1 (light) | AA |

### 7.2 焦点态 (Focus)

- 全局 `:focus-visible` 焦点环: `outline: 2px solid var(--color-ai); outline-offset: 2px;`
- 永远不要 `outline: none` 不替换
- 键盘 Tab 顺序: Header → CategoryNav → SearchBar → StatsPanel → HotspotGrid → Pagination → Footer

### 7.3 屏幕阅读器 (SR-only)

- 所有 icon 按钮必须有 `aria-label`
- 装饰性 SVG 标 `aria-hidden="true"`
- 状态变化 (`loading`, `error`) 必须 `aria-live="polite"`
- 倒计时 `aria-live="off"` (避免每秒打扰)

### 7.4 Reduced Motion

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## 8. 暗色 / 亮色双模 (Theme Lock)

### 8.1 切换方式

- 默认跟随 `prefers-color-scheme`
- 用户切换通过 Header 太阳/月亮图标
- 持久化到 `localStorage.hotspot-theme`

### 8.2 主题一致性

- **整个页面同一主题**, 不允许 1 个深色 + 1 个浅色混合
- 弹层 (Settings / Favorites) 跟随主主题
- 切换时仅 250ms 过渡 `background-color` / `color`,**不**触发动画重放

### 8.3 颜色一致性锁

每个组件用 `var(--color-{name})` 而非 hex。一次锁定 6 个类别色,全文不二次定义。

---

## 9. 性能 (Performance)

### 9.1 关键指标

| 指标 | 目标 | 测量 |
|------|------|------|
| LCP | < 2.5s | 第一张卡片渲染 |
| INP | < 200ms | 任意点击响应 |
| CLS | < 0.1 | 卡片入场不抖动 |
| JS bundle | < 250KB gzipped | 不引入大库 |

### 9.2 关键优化

- 图标: 用 `@phosphor-icons/react` 的 tree-shakable import, 每个图标 ~1KB
- 图表: Recharts 已是 tree-shakable,按需 import
- 图片: 无 (此项目纯文字卡片, 无图)
- 动画: 只用 `transform` + `opacity`,不 layout-thrashing
- 字体: 全部 `font-display: swap` + 系统等宽栈兜底

### 9.3 不做的事

- **不** 引入 Framer Motion (现 50KB+, 用 CSS 过渡 + 少量 Web Animations API)
- **不** 引入 Three.js / 任何 WebGL
- **不** 引入 Lottie / 复杂 SVG 动画

---

## 10. 验证清单 (Pre-flight Check)

部署前自查:

- [ ] 所有 `text-muted` 颜色用于 ≥14px 字号 或 非语义占位
- [ ] 卡片 border-left 颜色从 `var(--color-{cat})` 读, 不写 hex
- [ ] 数字 / 时间全部 `font-mono tabular-nums`
- [ ] 所有 icon 按钮有 `aria-label`
- [ ] 焦点态在 6 个路由页面一致
- [ ] 暗色 / 亮色下,所有 surface 颜色对比度 ≥ 4.5:1
- [ ] 移动端 320px 宽度无横向滚动
- [ ] reduced-motion 开启时无动画
- [ ] Lighthouse 分数 ≥ 90 (Performance / Accessibility / Best Practices / SEO)
- [ ] 控制台无 React 警告

---

## 11. 组件升级路线 (Component Upgrade Path)

### 11.1 已规划升级

| 组件 | 当前 | 目标 |
|------|------|------|
| `App.tsx` | 单 max-w-7xl 容器 | 顶部 bar + 主区 (stats+chart) + 列表区 3 段式 |
| `Header.tsx` | 13 个按钮, 部分手写 SVG | 13 个按钮, 全部用 @phosphor-icons/react |
| `CategoryNav.tsx` | 7 pill, 装饰色点 | 7 pill, 仅 active 有底色, 移除色点 |
| `HotspotCard.tsx` | border-top 2px + 顶角徽章 | border-left 2px 类别条 + 紧凑布局 |
| `HotspotGrid.tsx` | 4 col max | auto-fill 280px, 1/2/3/4 col 自适应 |
| `TrendChart.tsx` | 已修, github 已加 | 整体卡内 padding 调, 字号 11→10 |
| `StatsPanel.tsx` | 5 col grid | 5 col grid, 数值 12→13px 强化 |
| `index.css` | 旧 token | 引入 spacing scale, motion token, hover 升级 |

### 11.2 暂不升级 (本期范围外)

- SettingsPanel / FavoritesPanel / ItemDetailDialog (弹层视觉, 暂保持)
- Codegarden / Knowledge / Todos / Skills / Sync / WeeklyReport 等子页
- 这些用同一 token 系统, 但视觉细节下一轮再统一

### 11.3 不改的 (Section 11.F 永不改)

- 9 个路由的 URL 与 nav 标签
- API 契约 (`/api/*`)
- 6 个类别色 hex
- 字段命名 (snake_case 后端 → snake_case 前端)

---

## 12. 反例 (Anti-patterns, 已规避)

| 模式 | 规避方法 |
|------|---------|
| AI Purple 渐变 | 6 类别色均 ≥ 30% 饱和度,不用 `#7c3aed` |
| 三个等宽 card | HotspotGrid 用 auto-fill, 不固定 3 col |
| Hero 居中 + 网格背景 | 无 hero, 列表即主区 |
| 装饰状态点 | 移除 nav 前色点, 仅留必要 live 指示 (实时圆点) |
| Em-dash 装饰 | 标题用 ` · ` 或逗号, **不**用 `—` |
| 占位 `lorem ipsum` | 所有可见字符串中文,真实场景 |
| Scroll cue | 不显示"向下滚动"提示 |
| Scroll listener on window | 用 CSS 过渡 + IntersectionObserver |

---

**版本**: v4.0
**最后更新**: 2026-07-06
**维护者**: Hotspot Team
