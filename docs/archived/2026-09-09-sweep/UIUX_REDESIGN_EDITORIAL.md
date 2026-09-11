# SecNews Hotspot — Editorial 报纸风整站 UI/UX 重设计方案

> 版本: v1.0 · 2026-07-30
> 参考对象: https://agihunt.info/ （复古报纸 editorial 风格，实测样式数据驱动）
> 决策记录: ①报纸风为主 + 保留暗色「夜读」主题 ②全站分步推进 ③方案确认后直接落地实现

---

## 0. 设计立意

agihunt.info 的本质是**「AI 时代的报纸头版」**：米黄纸色、衬线标题、细线分栏、
首字下沉、反色分类 chip、零卡片零阴影——用最古典的版式语言承载最新的资讯流。

hotspot 与 agihunt 同为资讯聚合场景（安全/AI/金融/标讯多分类 feed），完全适配该语言。
本方案将 hotspot 从「暗色终端 HUD 风」迁移为「双主题报纸风」：

- **日报版（light，新默认）**: 米黄纸底 + 墨色衬线 + 砖红强调 —— 对齐 agihunt
- **夜读版（dark）**: 暖黑纸底 + 米白墨色 + 亮砖红 —— 同一版式语言的深色印刷品

核心原则：**信息用字号和字重分层，结构用细线和留白分隔，颜色只用于强调与分类**。

---

## 1. 视觉规范（Design Tokens）

唯一真相源仍为 `frontend/src/index.css`，Tailwind 全量映射变量，组件零裸色。

### 1.1 色彩 — 日报版 `[data-theme="light"]`（新默认）

| Token | 值 | 用途 | 对照 agihunt |
|---|---|---|---|
| `--bg-primary` | `#F6F1E6` | 页面纸底 | bg0 |
| `--bg-secondary` | `#FBF7EE` | 浅一档面板底 | bg1 |
| `--bg-card` | `#FBF7EE` | 卡片/输入框底 | bg1 |
| `--bg-hover` | `#EFE7D5` | hover 底 | bg2 |
| `--bg-elevated` | `#EFE7D5` | 弹层底 | bg2 |
| `--border-color` | `#CFC4AB` | 主分隔线 | line |
| `--border-light` | `#DDD3BD` | 次级分隔线 | linesoft |
| `--text-primary` | `#1A1610` | 主文字（墨色） | ink0 |
| `--text-secondary` | `#463E31` | 次级文字 | ink1 |
| `--text-muted` | `#7A6F5C` | meta 弱化文字（比 agihunt 的 #8A7F6C 加深一档，保 4.5:1 对比） | ink2 修正 |
| `--accent` | `#8E2318` | 强调色（砖红）：链接 hover/激活态/徽章 | accent |
| `--accent-soft` | `#F0E2DA` | 强调 hover 底 | accentsoft |
| `--accent-dim` | `#BB8D80` | 弱化强调 | accentdim |

### 1.2 色彩 — 夜读版 `[data-theme="dark"]`

同一版式的深色印刷品：暖黑而非冷黑（现有 `#0a0a0f` 偏蓝紫，废弃）。

| Token | 值 | 说明 |
|---|---|---|
| `--bg-primary` | `#181410` | 暖黑纸底 |
| `--bg-secondary` | `#1E1913` | |
| `--bg-card` | `#1E1913` | |
| `--bg-hover` | `#282118` | |
| `--bg-elevated` | `#2E261C` | |
| `--border-color` | `#3C3325` | |
| `--border-light` | `#32291E` | |
| `--text-primary` | `#EDE6D8` | 米白墨 |
| `--text-secondary` | `#B5A88F` | |
| `--text-muted` | `#8C7F68` | |
| `--accent` | `#D0684E` | 亮砖红（暗底对比 ≥4.5:1） |
| `--accent-soft` | `#3A241D` | |
| `--accent-dim` | `#8A5648` | |

### 1.3 分类色（双主题各一套，印刷油墨调）

| 分类 | light | dark | 语义 |
|---|---|---|---|
| ai | `#0B6E6E` | `#4FB8B8` | 青墨（保留品牌基因，降饱和） |
| security | `#A32014` | `#E07B6A` | 砖红系 |
| finance | `#8A6400` | `#D4B24A` | 赭金 |
| startup | `#5A4FA0` | `#A99BE0` | 紫墨 |
| bid | `#A65312` | `#E09B5E` | 橙墨 |
| general | `#2F7D4F` | `#6FBE93` | 绿墨 |
| github | `#5E4B8B` | `#AC99D6` | 堇紫 |

实现：`--color-ai` 等 7 个变量**移入各主题块内**（现在在 `:root` 全局，无法随主题切换）。
`types/index.ts` 的 `getCategoryColor` 改为返回 `var(--color-xxx)`，消除 TS 硬编码 hex 设计债；
`HotspotCard` 中 `${color}15` 拼透明度的写法改为 `color-mix(in srgb, var(--color-xxx) 12%, transparent)`。

### 1.4 状态色

| Token | light | dark |
|---|---|---|
| success | `#2F7D4F` | `#6FBE93` |
| warning | `#8A6400` | `#D4B24A` |
| error | `#A32014` | `#E07B6A` |
| info | `#0B6E6E` | `#4FB8B8` |

### 1.5 字体

```css
--font-serif: 'Newsreader', Georgia, 'Times New Roman', 'Songti SC', STSong, SimSun, serif;
--font-sans:  'Inter', system-ui, -apple-system, 'PingFang SC', 'Microsoft YaHei', 'Noto Sans SC', sans-serif;
--font-mono:  'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, monospace;
```

分工（对齐 agihunt 三套字体制）：
- **serif**: 报头、页面标题、feed 条目标题、正文摘要 —— 内容层
- **sans**: 导航、meta、按钮、表单、徽章 —— UI 层
- **mono**: 数字、时间戳、计数、代码 —— 数据层

### 1.6 字号阶梯

| 用途 | 规格 |
|---|---|
| 报头 masthead | `clamp(32px, 5vw, 52px)` / serif 700 / uppercase / `letter-spacing: 0.05em` |
| 头条标题 | `clamp(22px, 3vw, 32px)` / serif 700 / lh 1.25 |
| feed 条目标题 | `19px` / serif 700 / lh 1.35 |
| 区块标题 | `15px` / sans 700 / uppercase / ls 0.06em |
| 正文/摘要 | `15px` / serif 400 / lh 1.8 |
| UI 文字 | `13px` / sans |
| meta（来源·时间） | `11.5px` / sans / `--text-muted` / ls 0.02em |
| 徽章/chip | `10-12px` / sans 700 / ls 0.06em |

body 基准从 14px 提到 **15px**（阅读舒适度），`line-height 1.7`。

### 1.7 圆角 / 阴影 / 动效

- 圆角全面收紧（报纸无圆角）: `--radius-sm: 2px / md: 3px / lg: 6px / xl: 8px / full: 9999px`
- 阴影原则性归零：`--shadow-card: none`；仅弹层保留柔和投影
  （popover `0 4px 20px rgba(26,22,16,0.12)`，modal `0 16px 48px rgba(26,22,16,0.18)`）
- 动效时长/缓动 token 不变（120/200/320ms）；`prefers-reduced-motion` 全局降级保留
- 移除：`bg-glow-top` 顶部青色发光、`.corner-brackets` HUD 角标、`shadow-glow` 发光

### 1.8 间距 / 布局

- 间距 8 档 token 不变
- 内容容器: `max-width: 1280px; margin: 0 auto; padding: 0 32px`（移动端 16px）——对齐 agihunt `.wrap`
- 首页主体双栏: `grid xl:grid-cols-[minmax(0,1fr)_300px]`，主列右侧 `border-r 1px var(--border-color)` 竖分栏线；`<xl` 单列，侧栏内容降级到 feed 下方

---

## 2. 信息架构与导航重组

### 2.1 三层报头（替换现有单行 Header）

```
┌────────────────────────────────────────────────────────────┐
│ 2026年7月30日 星期四        待办 · 周报 · 知识库 · 同步 · 设置 │ ← 工具条 24px, sans 11px
├────────────────────────────────────────────────────────────┤
│                    S E C N E W S                            │ ← 报头 serif, 居中
│              安全 · AI · 金融 情报日报                        │ ← 副标语 meta
├────────────────────────────────────────────────────────────┤
│ [全部] 科技/AI 网络安全 金融 创业 招标 GitHub   🔍 ☆12 ◐    │ ← 吸顶分类条 44px
└────────────────────────────────────────────────────────────┘
```

1. **顶部工具条**（不吸顶）：左侧当日日期（mono）+ SSE 状态点；右侧次级功能链接
   （待办·周报·知识库·CodeGarden·同步·历史·技能·凭据·复盘·设置），"·" 分隔，
   当前路由项为 `--accent` + bold。移动端收纳为「更多 ▾」下拉。
2. **报头 masthead**：serif 大写 "SECNEWS" + 副标语。点击回首页。
   移除现 Header 中的渐变 logo 方块、v1.6 徽章（过时）、倒计时时钟等 HUD 元素；
   数据摄取状态（最近摄取 N 条）移到工具条右端 meta 文字。
3. **吸顶分类条**：`position: sticky; top: 0`，纸色实底 + `border-bottom 1px`，**不再毛玻璃**。
   分类 chip 矩形 `radius 2px`：激活态**反色**（墨底纸字 `#1A1610`/`#F6F1E6`），
   非激活透明底 + `1px` 边框。右端放搜索按钮、收藏计数、主题切换（☀/☾）、刷新。

### 2.2 页面路由逻辑（不改路由表，改导航呈现）

- 一级（分类条）: `/` + `/category/:cat` —— 内容消费主线
- 二级（工具条）: `/todos` `/weekly-report` `/knowledge` `/codegarden` `/sync` `/history`
  `/skills` `/secrets` `/reviews` —— 工作台功能
- 三级（内容内跳转）: `/deep/:type/:id`（深读）、`/brief`（简报）从 feed 条目进入
- 所有二级页面统一带「← 返回头版」面包屑（serif 小标题 + 细线下框）

### 2.3 首页信息架构（头版 = Front Page）

```
┌──────────────────────────────────┬───────────────┐
│ 【头条 Lead Story】               │  侧栏 300px    │
│  分类徽章 · 时间                   │ ┌───────────┐ │
│  头条大标题 (serif 28px)           │ │ 今日数据    │ │ ← StatsPanel 紧凑化
│  首字下沉摘要 max-w-[62ch]         │ │ 总数/分类计数│ │
│  来源 · ×N 相关                    │ ├───────────┤ │
├──────────────────────────────────┤ │ 7日趋势     │ │ ← TrendChart 瘦身
│ 排序工具行: 最新|最热|上升  ·日报    │ ├───────────┤ │
├──────────────────────────────────┤ │ 待办 (N)    │ │
│ ▸ 条目标题 (serif 19px)           │ ├───────────┤ │
│   摘要一行 · 来源 · 2小时前 · ×3   │ │ 近7天归档   │ │ ← 日期链接列表
│ ──────────────────────────────── │ │ (→/history)│ │
│ ▸ 条目标题                        │ └───────────┘ │
│ ──────────────────────────────── │               │
│ ▸ … (细线分隔, 无卡片)             │               │
└──────────────────────────────────┴───────────────┘
```

UX 改进点：
- **头条自动提升**: feed 第一条（当前排序最高权重）升级为 lead story 版式
- **搜索改为按需展开**: 分类条右端 🔍 点开行内展开搜索框（`/` 快捷键聚焦），
  替代现在常驻整行的 SearchBar —— 减少首屏噪音
- **时间范围**（24h/3d/7d）与搜索框同行，收进排序工具行
- StatsPanel/TrendChart 从主列抽出移入侧栏 —— 主列只留内容流，滚动路径变短
- 收藏星、状态点等操作元素保留在条目行右端，hover 才完全显影（减少视觉噪音）

### 2.4 二级页面版式基调

全部二级页面共用「版面页」模板：serif 页面大标题 + 细线下框 + sans 工具行 +
细线分隔的内容区。现有卡片网格类页面（知识库/CodeGarden/同步）保持栅格结构，
但卡片降为「纸面分格」：`bg-card` 纸底 + 1px 细线 + 2px 圆角 + 无阴影。

---

## 3. 组件规范（核心组件逐一定义）

### 3.1 HotspotCard → EditorialRow（feed 条目行）

- 结构: `<article class="feed-row">`，`border-bottom: 1px solid var(--border-color)`，
  `padding: 18px 0`，透明底，无圆角无阴影
- 行内布局: 左列内容 + 右端操作列（收藏星/状态）
- 标题: serif 19px/700 墨色，`hover → var(--accent)`，无下划线
- 摘要: serif 14px `--text-secondary`，line-clamp-2
- meta 行: sans 11.5px `--text-muted`: `分类徽章 · 来源 · 相对时间 · 质量分`
- 分类徽章: 2px 圆角描边款 —— `1px solid 分类色` + 分类色文字 + 透明底，
  sans 10px/700 uppercase（替换现在的 15% 透明底胶囊）
- 聚簇标注: `×N` 徽章，`1px solid var(--accent)` + accent 文字 + 2px 圆角，
  hover 底 `--accent-soft`（对齐 agihunt）
- 收藏星: 默认 `--text-muted` 40% 透明度，row hover 时显影，已收藏恒为 `--accent`

### 3.2 头条 LeadStory

- 标题 serif `clamp(22px,3vw,32px)`，摘要段 `max-w-[62ch]` +
  **首字下沉**: `::first-letter { font-size: 2.9em; font-weight: 700; color: var(--accent); float: left; }`
- 底部 `border-bottom: 2px solid var(--text-primary)`（头版粗规线，与普通细线区分）

### 3.3 cat-pill（分类 chip）

- `border-radius: 2px; padding: 6px 13px;` sans 12px
- 非激活: 透明底 + `1px solid var(--border-color)` + `--text-secondary`
- hover: `background: var(--bg-hover)`
- 激活: **反色** `background: var(--text-primary); color: var(--bg-primary); font-weight: 700`
- 分类计数用 mono 小字随排

### 3.4 排序/时间 toggle

- 去容器盒（现 time-toggle 是嵌盒式），改 agihunt 下划线式:
  文字按钮，激活态 `border-bottom: 1.5px solid var(--accent)` + accent 文字 + bold

### 3.5 按钮体系

| 类 | 规格 |
|---|---|
| `.btn-primary` | 墨底纸字反色，2px 圆角，hover 微调亮度 |
| `.btn-ghost` | 透明底 1px 边框，hover 边框转 `--text-muted`（保留现类名，改样式） |
| `.btn-accent` | accent 描边 + accent 字，hover 底 `--accent-soft` |

### 3.6 表单（editorial-input / select / search）

- `background: var(--bg-secondary)`，`border: 1px solid var(--border-color)`，2px 圆角
- focus: `border-color: var(--accent)` + `box-shadow: 0 0 0 3px color-mix(accent 15%)`

### 3.7 弹层（modal / drawer / toast / popover）

- 纸底 + 1px 边框 + 6px 圆角 + 柔和投影（阴影体系中唯一保留处）
- 遮罩 `rgba(26,22,16,0.5)`（墨色而非纯黑）

### 3.8 数据可视化（TrendChart/StatsPanel/echarts/recharts）

- 图表配色切换为分类墨色系；网格线 `--border-light`；文字 `--text-muted` sans 11px
- 侧栏内 TrendChart 高度压缩至 ~160px，隐藏图例改 tooltip

### 3.9 状态组件

- LoadingSkeleton: shimmer 底色改纸色系（`--bg-hover` ↔ `--bg-secondary`）
- PageFallback: 去掉终端 `>` 前缀风格，改居中 serif "正在排版…" + 细线
- EmptyState: serif 标题 + meta 说明 + btn-ghost 动作

---

## 4. 交互细节

| 场景 | 行为 |
|---|---|
| 主题切换 | 分类条右端 ☀/☾，`data-theme` + localStorage 机制不变；默认值改 `light` |
| feed hover | 标题变 accent（120ms）；操作列显影；**无位移无阴影**（去掉卡片上浮） |
| 搜索 | 🔍 点击/`/` 键展开行内输入框，`Esc` 收起，防抖 300ms 不变 |
| 分页 | 保留分页按钮（btn-ghost 化）+ 页码 mono |
| 收藏 | 乐观更新逻辑不变；星标色 `--accent` |
| SSE 状态 | 工具条左端实心/空心圆点 + "实时"/"轮询" meta 字 |
| 刷新 | 分类条右端 ↻，旋转动画保留 |
| 焦点 | 全局 `:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px }` |
| 键盘 | Tab 顺序 = 视觉顺序；chip 组 `role="tablist"` 方向键切换（渐进增强） |

### 无障碍验收基线

- 正文/标题对墨纸对比 ≥ 12:1；meta 文字 ≥ 4.5:1（`#7A6F5C` on `#F6F1E6` = 4.6:1）
- accent `#8E2318` on `#F6F1E6` = 7.2:1（AA 大小字全过）
- 所有 icon-only 按钮补 `aria-label`；分类条 `nav` 语义；feed 用 `article`+`h2/h3` 层级
- `prefers-reduced-motion` 全局降级保留

---

## 5. 性能承诺（UX 第 3 点）

- 零新增运行时依赖（无组件库/无字体包新增；Newsreader 已在栈内，系统 serif 兜底）
- 主题切换仍为纯 CSS 变量翻转，无重渲染成本
- 阴影/毛玻璃（backdrop-filter）大量移除 → 合成层减少，滚动性能提升
- 懒加载路由结构不动；首屏主列内容前置、图表移侧栏后 LCP 元素变为文本（渲染更快）

---

## 6. 分步实施计划（全站推进）

| 步骤 | 范围 | 关键文件 | 验证 |
|---|---|---|---|
| S1 token 重构 | 双主题全量变量 + 基础类（body/滚动条/selection/焦点环） | `index.css` | build + 视检双主题 |
| S2 映射与全局 | tailwind 字体映射、`getCategoryColor` 变量化、PageLayout 容器/背景 | `tailwind.config.js` `types/index.ts` `PageLayout.tsx` | build + 单测 |
| S3 报头导航 | 三层报头（工具条/masthead/吸顶分类条）、CategoryNav chip 化、SearchBar 收纳 | `Header.tsx` `CategoryNav.tsx` `SearchBar.tsx` | 视检 + 响应式 |
| S4 头版信息流 | LeadStory + EditorialRow + 双栏栅格 + 侧栏（Stats/Trend/近7天） | `App.tsx(HomePage)` `HotspotCard.tsx` `HotspotGrid.tsx` `StatsPanel.tsx` `TrendChart.tsx` | 视检 + 单测 |
| S5 知识库页 | 版面页模板 + knowledge-area-card 纸面化 | `KnowledgePage.tsx` + knowledge/* | 视检 |
| S6 其余页面 | todos/history/weekly/codegarden/sync/settings/favorites 等批量适配（多数吃 token 红利，重点清理残留裸色与 HUD 元素） | 各页组件 | 视检 |
| S7 总验证 | `npm run build` + `vitest` 全量 + 375/768/1280/1536 四档响应式 + 双主题对比度抽查 | — | 全绿 |

每步一次本地 commit，可随时回退。

---

## 7. 明确不做

- 不改后端 API、不改路由表、不改数据 hooks 逻辑
- 不引入组件库（shadcn/radix）与新依赖
- 不做 agihunt 的 Jobs/登录/EN 等 hotspot 不存在的功能
- echarts/recharts 双库并存问题不在本次范围（仅改配色）
