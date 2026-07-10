# 热点地图设计规范

> 基于 design-taste-frontend 审美优化体系，为热点地图（Hotspot Map）项目定制的设计规范文档。
> 三旋钮设定：`DESIGN_VARIANCE: 5` | `MOTION_INTENSITY: 3` | `VISUAL_DENSITY: 8`

---

## 一、设计理念

### 1.1 定位

热点地图是一个**高密度数据聚合看板**，面向技术/分析型用户，核心目标是让用户在最短时间内获取多领域热点全貌。设计语言围绕**暗色技术美学 + 克制动效 + 座舱级信息密度**展开。

### 1.2 设计读取

> Reading this as: a tech dashboard / data aggregation tool for analytical users, with a dark-tech hacker aesthetic, leaning toward a cockpit-level data density with restrained motion and subtle visual refinement.

### 1.3 设计原则

| 原则 | 说明 |
|------|------|
| **信息优先** | 所有视觉决策以提升信息获取效率为第一目标，装饰性元素让位于内容 |
| **色彩即分类** | 每个分类有独立标识色，用户通过颜色即可快速定位所属领域 |
| **克制即高级** | 无色发光、无装饰动画、无冗余标签，每一像素都有功能 |
| **紧凑不拥挤** | DENSITY 8 意味着高密度，但通过精确的间距、分隔线和字体层级保持清晰 |
| **双主题对等** | 暗色与亮色主题体验一致，无信息损失 |

---

## 二、三旋钮体系

### 2.1 DESIGN_VARIANCE: 5

对称布局，CSS Grid 等宽列。左侧 Logo + 标题，右侧控制区，标准的仪表盘顶部栏结构。各组件在垂直方向线性排列，无重叠、无偏移、无不对称裁切。

**规则：**
- 所有内容区域使用 `max-w-7xl mx-auto` 居中约束
- 卡片网格等宽排列（`grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4`）
- 不使用 masonry、重叠、偏移等高方差布局手法

### 2.2 MOTION_INTENSITY: 3

只有功能性的过渡动画，无装饰性动效。

**允许的动效：**
- 卡片进入时的 `fade-in + translateY(6px)` 交错出现
- 主题切换的 `background-color 0.25s ease` 过渡
- 按钮 hover 的 `border-color / background-color 0.15s ease` 过渡
- 进度条的 `width 0.5s ease-out` 变化
- 骨架屏的 `shimmer` 扫描线动画

**禁止的动效：**
- 无限循环动画（除了状态指示脉冲）
- 视差滚动
- 鼠标跟踪/磁吸效果
- 页面转场动画
- 装饰性浮动/呼吸动画

### 2.3 VISUAL_DENSITY: 8

座舱级信息密度。

**规则：**
- 卡片 padding: `16px`（`p-4`）
- 卡片间距: `14px`（`gap-3.5`）
- 标题字号: `13px`
- 正文字号: `11px`
- 辅助信息字号: `10px`
- 不使用卡片外发光来区分层级——用 `border-top` 彩色边线 + 细边框 + 紧凑间距来区分

---

## 三、色彩系统

### 3.1 分类色板

| 分类 | 色值 | 用途 |
|------|------|------|
| 科技/AI | `#00bcd4`（青蓝） | 卡片顶部边线、分类标签、激活态 |
| 网络安全 | `#e85d5d`（柔红） | 同上 |
| 金融/投资 | `#f0c929`（金黄） | 同上 |
| 独立开发/创业 | `#7c6aff`（紫蓝） | 同上 |
| 招标资讯 | `#e8891a`（橙） | 同上 |
| 综合热点 | `#00c96a`（翠绿） | 同上，同时用于"全部热点"导航和导出链接 |

**使用规则：**
- 分类色仅用于标识该分类的元素，不混用
- 色彩饱和度已控制在中等水平，不产生视觉疲劳
- 所有分类色在暗色和亮色主题中保持一致

### 3.2 主题色板

**暗色主题：**

| Token | 色值 | 用途 |
|-------|------|------|
| `--bg-primary` | `#0a0a0f` | 页面背景 |
| `--bg-card` | `#111118` | 卡片/面板背景 |
| `--bg-hover` | `#181825` | hover/进度条背景 |
| `--bg-elevated` | `#1c1c2e` | 弹窗/悬浮层背景 |
| `--border-color` | `#1e1e30` | 标准边框 |
| `--border-subtle` | `rgba(255,255,255,0.04)` | 弱分割线 |
| `--text-primary` | `#e8e8ee` | 主标题/正文 |
| `--text-secondary` | `#8888a0` | 次要信息 |
| `--text-muted` | `#555568` | 辅助/置灰信息 |

**亮色主题：**

| Token | 色值 | 用途 |
|-------|------|------|
| `--bg-primary` | `#f4f4f8` | 页面背景 |
| `--bg-card` | `#ffffff` | 卡片/面板背景 |
| `--bg-hover` | `#eeeef4` | hover/进度条背景 |
| `--bg-elevated` | `#e8e8f0` | 弹窗/悬浮层背景 |
| `--border-color` | `#dcdce6` | 标准边框 |
| `--border-subtle` | `rgba(0,0,0,0.04)` | 弱分割线 |
| `--text-primary` | `#1a1a2e` | 主标题/正文 |
| `--text-secondary` | `#555570` | 次要信息 |
| `--text-muted` | `#9999aa` | 辅助/置灰信息 |

### 3.3 色彩禁忌

- 禁止使用纯黑 `#000000` 和纯白 `#ffffff`——使用 off-black/off-white 保持深度
- 禁止外发光（`box-shadow` 发光）——使用内边框 + 半透明背景区分层级
- 禁止渐变色标题——标题使用纯色
- 每个项目只使用一套中性色——不混用暖灰和冷灰

---

## 四、排版规范

### 4.1 字体

```css
font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
```

等宽字体作为主字体，与暗色技术美学一致。全站统一使用，无衬线/衬体混用。

### 4.2 字号层级

| 用途 | 字号 | 字重 | 行高 | 字间距 |
|------|------|------|------|--------|
| 页面标题（h1） | 18px | 700 | tight | `tracking-tight` |
| 卡片标题 | 13px | 500 | 1.6 | normal |
| 正文/摘要 | 11px | 400 | 1.5 | normal |
| 辅助信息 | 10px | 400 | 1.4 | normal |
| 导航按钮 | 13px | 500/600 | 1.4 | normal |
| 统计标签 | 11px | 600 | 1.4 | `0.08em` uppercase |

### 4.3 排版规则

- 卡片标题最多 2 行截断（`line-clamp-2`）
- 摘要最多 2 行截断
- 全站使用 `-webkit-font-smoothing: antialiased` 优化字体渲染
- 不出现 em-dash（`—`），仅使用连字符 `-`

---

## 五、组件规范

### 5.1 卡片（card-base）

```css
.card-base {
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md); /* 10px */
  box-shadow: var(--shadow-card);
}
```

**交互状态：**
- Default: 细边框 + 轻微阴影
- Hover: 边框变亮、阴影加深
- Active: `scale(0.99)` 物理按压反馈

**热点卡片特殊规则：**
- 顶部 `2px` 彩色边线标识分类
- 底部 `border-subtle` 分隔来源和操作区
- 不显示评分标签
- 不显示彩色圆点作为装饰

**实现状态**：卡片顶部 2px 彩色边线 + 底部 `border-subtle` 分隔来源与操作区；列表页与导出页均不显示 HOT/WARM/NEW 评分标签，分类身份由顶部边线颜色单独承担。

### 5.2 按钮

**幽灵按钮（btn-ghost）：**

```css
.btn-ghost {
  background: transparent;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  border-radius: var(--radius-sm); /* 6px */
}
```

**交互状态：**
- Default: 透明背景 + 灰色边框
- Hover: 背景 `var(--bg-hover)` + 文字 `var(--text-primary)`
- Active: `scale(0.97)` 按压反馈
- Focus-visible: 2px 青色轮廓环

**导航分类按钮：**
- 非激活：透明背景 + 标准边框
- 激活：半透明分类色背景 + 分类色边框 + 分类色文字
- 圆角：`var(--radius-sm)`

### 5.3 分类标签（badge）

```css
.badge {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  border-radius: var(--radius-full);
  padding: 2px 8px;
}
```

分类标签使用 `背景色 8% 透明度 + 纯色文字` 的组合。

### 5.4 搜索输入框

- 标签位于输入框上方（禁止 placeholder-as-label）
- 输入框背景 `var(--bg-card)`，边框 `var(--border-color)`
- 清除按钮为 SVG X 图标
- 搜索图标为 SVG 放大镜

### 5.5 统计进度条

- 高度：4px
- 背景：`var(--bg-hover)`
- 填充：对应分类色，无外发光
- 圆角：`var(--radius-full)`

### 5.6 趋势图

- 使用 Recharts `BarChart`，堆叠柱状图
- 网格线：虚线，色值 `var(--border-color)`
- 柱体圆角：顶部 2px
- 图例：圆点 + 文字，位于图表下方
- 自定义 tooltip：使用 `var(--bg-elevated)` 背景

---

## 六、导航栏规范

- 导航按钮水平排列，`flex-wrap` 允许换行
- 每个导航项包含：分类色圆点 + 标签 + 计数徽标
- 激活态：分类色边框 + 半透明背景
- 非激活态：透明背景 + `var(--border-color)` 边框
- hover 态：`var(--bg-hover)` 背景

---

## 七、动效规范

### 7.1 允许的动画列表

| 动画 | 触发时机 | 参数 |
|------|---------|------|
| `fade-in` | 卡片进入视口 | 0.4s cubic-bezier(0.16, 1, 0.3, 1) |
| `shimmer` | 骨架屏加载 | 1.5s ease-in-out infinite |
| `pulse-dot` | 状态指示点 | 2s ease-in-out infinite |
| `slide-up` | 面板出现 | 0.4s cubic-bezier(0.16, 1, 0.3, 1) |
| 过渡 | 主题切换 | 0.25s ease |
| 过渡 | hover/active | 0.15s ease |

### 7.2 交错延时

卡片网格中使用 `delay-1` 到 `delay-10` 类，每个间隔 40ms：

```
delay-1: 40ms | delay-2: 80ms | delay-3: 120ms
delay-4: 160ms | delay-5: 200ms | ...
```

### 7.3 可访问性

所有动画受 `prefers-reduced-motion` 媒体查询保护，用户启用减少动效后：

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

## 八、可访问性规范

### 8.1 对比度

- 正文文字：WCAG AA 最低 4.5:1（暗色主题 `#e8e8ee` on `#0a0a0f` 远超标准）
- 大标题（18px+）：WCAG AA 最低 3:1
- 所有交互元素需有可见的 focus 状态

### 8.2 焦点管理

所有可交互元素使用 `focus-ring` 类：

```css
.focus-ring:focus-visible {
  outline: 2px solid var(--color-ai);
  outline-offset: 2px;
}
```

### 8.3 视口稳定性

- 使用 `min-h-[100dvh]` 而非 `h-screen`，防止移动端地址栏折叠导致布局跳跃
- 页面滚动条宽度 5px，不占用布局空间（`overflow: overlay`）

---

## 九、代码规范

### 9.1 CSS 变量命名

```
--bg-*       → 背景色
--text-*     → 文字色
--border-*   → 边框色
--color-*    → 分类色
--radius-*   → 圆角
--shadow-*   → 阴影
--accent-*   → 强调色（语义化）
```

### 9.2 类名约定

```
.card-base    → 卡片容器
.btn-ghost    → 幽灵按钮
.badge        → 分类标签
.dot-indicator → 状态指示点
.focus-ring   → 焦点轮廓
.animate-*    → 动画
.delay-*      → 动画延时
```

### 9.3 禁止模式

| 模式 | 替代方案 |
|------|---------|
| emoji 图标 | 内联 SVG（Phosphor 风格路径） |
| `·` 中间点分隔 | 换行或 `|` |
| 外发光 box-shadow | 内边框 + tinted shadow |
| 装饰性圆点 | 仅用于语义状态 |
| placeholder 替代 label | label 元素位于输入框上方 |

---

## 十、主题系统

### 10.1 主题切换

- 使用 `data-theme` 属性控制（`dark` / `light`）
- 切换逻辑：点击按钮 → 设置 `document.documentElement.dataset.theme` → `localStorage` 持久化
- 默认主题：dark
- 尊重 `prefers-color-scheme` 媒体查询（通过 `localStorage` 覆盖）

### 10.2 亮色主题适配

亮色主题不是暗色的"反色"，而是一套独立设计的色板：
- 背景从深灰变为浅灰（`#f4f4f8`），而非纯白
- 卡片使用纯白背景 + 浅灰边框
- 阴影从深色变为浅色（`rgba(0,0,0,0.04)`）
- 分类色保持不变，确保跨主题一致性

---

## 附录：修改记录

| 日期 | 变更内容 |
|------|---------|
| 2026-07-04 | 初始版本，基于 design-taste-frontend SKILL.md 规范建立 |
| 2026-07-04 | 网络安全采集器升级 v3：新增 20+ 信息源，涵盖 Krebs on Security / PortSwigger Research / SANS ISC / 安全客 / FreeBuf / 奇安信 / 360 Netlab / 腾讯安全 / CNNVD 等，备用数据 40 条覆盖漏洞/攻击/泄露/政策/行业五大类 |
| 2026-07-04 | 移除"已移除"反例表述，热点卡片规则改为"实现状态"描述 |

---

## 参考文档

- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [SPEC.md](./docs/SPEC.md)
- [CHECKLIST.md](./docs/CHECKLIST.md)
- [TASKS.md](./docs/TASKS.md)
- [DESIGN_GUIDE.md](./DESIGN_GUIDE.md)
