# SECNEWS 三层报纸 — 全站 UI 方案 v2.0

> 日期：2026-08-18 · 状态：提案（附可交互 demo：`index.html`）
> 依据：`PROJECT.md`（三层架构）、`docs/UIUX_REDESIGN_EDITORIAL.md`（报纸风视觉基线）、`docs/hotspot_v1.7_PRD.md`（用户工作流）、`knowledge/SOUL.md`（用户画像）

---

## 0. 设计上下文（Design Context）

| 维度 | 内容 |
|---|---|
| 目标用户 | 安全 × AI 交叉领域从业者 / 独立开发者，单人本地工作站，重度键盘使用者 |
| 关键任务 | ① 早间扫描头版热点 ② 收藏→判断→整理进知识库 ③ 周末精炼概念/写周报 ④ 标讯订阅与投标提醒 ⑤ CodeGarden 项目执行与复盘 |
| 品牌约束 | 双主题报纸风（日报版 light 默认 / 夜读版 dark）；分类七色为语义系统非装饰；零卡片零阴影的 editorial 版式语言；Newsreader 衬线 + sans UI 层 + mono 数据层三字体制 |
| 产品理念 | 第二大脑三层架构：资料层（我有什么）→ 判断层（我怎么看）→ 行动层（我做什么），知识复利闭环 raw → refine → link → structure → publish |

**本方案的核心主张**：现有 editorial 方案（2026-07-30）与三层架构（2026-08-06 决策）尚未合流——前者仍按「分类」组织导航，后者只有模块划分没有视觉语言。本方案把两者焊接为**「三层报纸」**：用报纸的「版面」隐喻承载三层认知模型，信息架构三层化，视觉语言完全继承已定稿的 editorial tokens（品牌约束不破坏）。

**AI Slop Test 自检**：本界面的记忆点是「一个像日报头版的情报工作站」——报头、期号（VOL.070）、版次标记（头版/评论版/排稿版）、首字下沉、细线分栏。不是深色 HUD，不是青紫渐变，不是万物卡片。

---

## 1. 信息架构（IA）

### 1.1 三层导航 = 报纸的三个版面

```
┌─────────────────────────────────────────────────────────────┐
│ 工具条（不吸顶）：日期·SSE 状态 | 待办·周报·知识库·CodeGarden… │  24px
├─────────────────────────────────────────────────────────────┤
│ 报头 SECNEWS · 副标语 · 期号/版次标记（点击回头版）              │
├─────────────────────────────────────────────────────────────┤
│ 吸顶版次条（sticky）：[资料层·头版][判断层·评论版][行动层·排稿版] │  44px
│   （+ 深读·副刊）                        ★12  ↻  ☀/☾        │
│ 分类条（仅头版）：全部|安全|AI|金融|创业|招标|GitHub + 行内搜索   │
└─────────────────────────────────────────────────────────────┘
```

版次隐喻映射（也是报头下的 edition-mark）：

| 层 | 版面名 | 隐喻 | 回答 |
|---|---|---|---|
| 资料层 `/data/*` | 头版 Front Page | 今天的报纸：头条 + 资讯流 + 侧栏数据 | 我有什么 |
| 判断层 `/judge/*` | 评论版 Editorial Desk | 编辑部：门禁、趋势、图谱、阅读模式 | 我怎么看 |
| 行动层 `/action/*` | 排稿版 Composing Room | 排稿间：待办、提醒、报告、项目 | 我做什么 |

### 1.2 页面树

```
资料层（头版）
├── 头版 feed：LeadStory（权重最高条目升格）+ EditorialRow 流 + 侧栏
│   （今日数据 / 7日趋势 / 待办速览 / 近7天归档）
├── 分类筛选（chip，二级）、搜索（行内 / 快捷键）、时间范围（24h/3d/7d）
├── 收藏夹 / 历史 / 知识导入 / 标讯地区筛选
└── 深读视图（副刊）：从任意条目进入，66-72ch 单栏 + 首字下沉 + 落款动作条

判断层（评论版）
├── 阅读模式四联：简报 Brief / 扫描 Scan / 深度 Deep / 告警 Alert
├── 质量门禁台（13 道 Gate 拒稿/折叠/通过流水表）
├── 趋势 · 注意力热力 · 标讯分析（地区/业务线分布）
└── 知识图谱（98 概念）· 知识编译

行动层（排稿版）
├── 今日焦点（由判断层推送：标讯提醒 D-N / 周报待生成 / 待办）
├── 待办 · 投标提醒 · 报告生成
├── 知识复利：raw→refine→link→structure→publish 进度 · 整理箱 · SM-2 复习
└── CodeGarden 项目 · 服务网格 · 技能 · 复盘
```

### 1.3 关键任务动线（对照 PRD 用户工作流）

早间扫描：头版 → 一屏内完成「头条判断 + 分类切换 + 收藏」；侧栏待办/趋势不抢占主列注意力。收藏进库：条目星标（乐观更新）→ 深读页「收藏到知识库 / 关联概念」→ 判断层图谱呈现。周末输出：行动层复利进度条 → 编译本周概念 → 周报生成。跨层联动沿用已定决策：URL search params 传参（可分享、可持久化），面包屑「← 返回头版」贯穿二级页。

IA 原则：分类是**过滤器**（chip），不是顶层导航；层才是导航。这与 2026-08-06 决策日志一致（避免领域分类导航碎片化）。旧路由 `/category/:cat` → `/data?category=`，`/knowledge/*` 按四领域拆入判断/行动层。

---

## 2. 视觉方向

### 2.1 一句话定位

「米黄纸底上的墨字情报日报」：信息用字号字重分层，结构用细线留白分隔，颜色只用于强调与分类。双主题 = 同一版式的日间印刷品与夜间印刷品。

### 2.2 色彩（tokens 完全继承 editorial 定稿值，双主题各一套）

| Token | 日报版 | 夜读版 | 用途 |
|---|---|---|---|
| bg-primary | `#F6F1E6` | `#181410`（暖黑） | 纸底 |
| bg-secondary / hover | `#FBF7EE` / `#EFE7D5` | `#1E1913` / `#282118` | 面板 / 悬停 |
| border-color / light | `#CFC4AB` / `#DDD3BD` | `#3C3325` / `#32291E` | 细线体系 |
| text-primary | `#1A1610`（墨） | `#EDE6D8`（米白墨） | 标题正文，对比 ≥12:1 |
| text-muted | `#7A6F5C` | `#8C7F68` | meta，≥4.5:1 |
| accent 砖红 | `#8E2318`（7.2:1） | `#D0684E`（≥4.5:1） | 唯一强调色：链接 hover / 激活 / 星标 |

分类七色（印刷油墨调，随主题切换）：ai 青墨、security 砖红系、finance 赭金、startup 紫墨、bid 橙墨、github 堇紫、general 绿墨。色值见 demo 规范页；实现上 `--color-*` 移入各主题块，`getCategoryColor` 返回 `var()`。

### 2.3 字体三进制（品牌约束）

serif（Newsreader + Songti SC 兜底）承载内容层：报头、头条、条目标题、摘要、深读正文；sans（IBM Plex Sans/PingFang）承载 UI 层：导航、按钮、表单、徽章、meta；mono（JetBrains Mono）承载数据层：时间、计数、质量分、金额、日期。字号阶梯 8 档 + `clamp()` 流体报头（demo 规范页可逐档核验）。

### 2.4 空间与形状

圆角收紧 2/3/6/8px；阴影原则性归零，仅弹层保留两级柔和投影（遮罩为墨色而非纯黑）；头版双栏 `1fr + 300px`，主列右侧细线竖分栏；条目流零卡片——`border-bottom` 细线分隔 + 18px 垂直节奏；区块标题用「大写 sans + 右延细线」替代框容器。

### 2.5 动效

时长 token 120/200/320ms，缓动统一 ease-out-quart；只动状态（颜色/透明度/宽度），不动布局（无位移、无上浮、无发光）；页面切换 320ms 淡入上移 6px；`prefers-reduced-motion` 全局降级为 0.01ms。

---

## 3. 组件状态规范

每个组件定义七态：default / hover / active / focus-visible / disabled / loading / data 异常态（empty·error·skeleton）。全部在 demo「设计规范」页可交互核验。

### 3.1 层导航 layer-tab（全站最高频）

| 状态 | 规格 |
|---|---|
| default | text-secondary，底部 2.5px 透明边 |
| hover | accent 字 + bg-hover 底（120ms） |
| active | accent 字 + accent 底边 2.5px，副标签（我有什么/怎么看/做什么）同排 |
| focus-visible | 全局 2px accent outline + 2px offset |
| 键盘 | tablist 语义，方向键切换（渐进增强） |

### 3.2 分类 chip cat-pill

default：透明底 + 1px border-color + 计数 mono 小字；hover：bg-hover；active：**反色**（墨底纸字加粗）——报纸的「已选版」隐喻；不设 disabled（分类恒可用）。行内搜索 `/` 聚焦，Esc 收起，300ms 防抖。

### 3.3 Feed 条目行 EditorialRow

default：标题 serif 19px 墨色，操作列（星/已读）35% 透明；hover：标题转 accent、操作列显影，无位移无阴影；已读：标题降为 text-secondary；聚簇：×N 描边徽章，hover 底 accent-soft；已收藏：星标恒为 accent（不随行失焦淡出）；低质（Q<70）：Q 徽章 err 描边，**行不隐藏不删除**（质量红线 1）；加载：纸色 shimmer 骨架（四行结构：meta/标题/摘要/图位）。

### 3.4 按钮（三类）

primary 墨底纸字（hover 提亮 12%、active 下沉 1px、loading 内嵌旋转环且文字隐藏、disabled 40% 透明）；ghost 1px 边框（hover 边框转 text-muted）；accent 砖红描边（hover 底 accent-soft）。全部 2px 圆角。

### 3.5 表单

input/select：bg-secondary 底 + 1px 边 + 2px 圆角；focus：accent 边 + 3px 15% accent 光环（唯一「光环」，替代发光装饰）；error：err 边 + 红字 hint（文案说清规则，如「至少 6 个字符且不含停用词」）；disabled：50% 透明。敏感字段未解锁恒显 `******`（红线 8）。

### 3.6 状态反馈

toast：纸底 + 1px 边 + 左 3px 语义色条（成功绿/失败红/信息青），8px 圆角 + 柔投影，失败 toast 必带「重试」动作；empty：serif 标题 + meta 说明 + ghost 动作按钮，且**教育用户下一步**（「放宽时间范围到近 7 天」）；skeleton：bg-hover↔bg-secondary 纸色 shimmer；表格行 hover：bg-hover 底；状态徽章五档：p-ok/p-warn/p-err/p-info 描边款 + p-solid 反色款。

### 3.7 数据可视化

图表线色 = 分类墨色，网格线 border-light，轴字 mono 9-11px；侧栏趋势图压缩至 160px、隐藏图例改 tooltip；注意力热力用 accent 与纸底的 color-mix 四档；标讯分布用 bid 橙墨横条，宽度 320ms ease-out-quart 过渡。

### 3.8 无障碍验收基线

正文/标题对纸底 ≥12:1；meta ≥4.5:1；accent 大小字全过 AA；全部 icon-only 按钮有 aria-label；导航 nav/tablist 语义、feed 用 article + h2/h3 层级；Tab 顺序 = 视觉顺序；reduced-motion 降级；快捷键 `/` 搜索、`T` 切主题、`R` 刷新（均避开输入焦点）。

---

## 4. Demo 说明

`index.html`（零依赖单文件，Google Fonts 缺网时自动回退系统衬线）：五个视图 hash 路由——`#front` 头版 / `#judge` 判断层 / `#action` 行动层 / `#read` 深读 / `#spec` 设计规范；可交互项：主题切换（持久化）、分类筛选、搜索、排序 toggle、星标收藏、快捷键 `/` `T`。落地实施对齐 editorial 方案的 S1–S7 分步计划（token 重构 → 报头导航 → 头版 → 其余页面批量适配），前端唯一真相源仍为 `frontend/src/index.css`。

## 5. 明确不做

不改后端 API 与路由表；不引入组件库与新运行时依赖；不做 HUD 残留（青色发光、角标、倒计时钟）；不做移动端功能裁剪（<1100px 侧栏降级到主列下方，<768px 分类条横滑、工具条收纳为「更多 ▾」）。
