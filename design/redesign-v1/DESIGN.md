# Hotspot 全站前端重构 · 风格契约与覆盖矩阵

> **版本**: redesign-v1（2026-11-17，基于 v0.8.9 代码事实 + 单一权威 PRD）
> **交付物**: `index.html`（全站可交互 demo）· `canvas.html`（无限画布）· 本文档
> **落点**: `design/redesign-v1/` —— **不触碰 `frontend/src/` 生产代码**；落地须按本文「落地路线」分批接入并过 CI 门禁
> **数据底账**: `design/_research/`（routes-status.md / prd-capabilities.md / frontend-visual.md，2026-11-17 实测）

---

## 1. 风格选型：哨兵编辑部 × 安全终端

**一句话**：在仓库已确立的「编辑部形态」（DEV-0181 报头/版面条/印务条）与安全终端数据纪律之上做**全站统一精化**，不另起炉灶。

**为什么是它**（四条依据）：

1. **产品定位**：面向安全从业者的单人本地工作台——数据密集、证据账本、门禁/回执语义。需要的是可扫读的遥测终端，不是营销页。
2. **既有资产**：壳已是编辑部三段（masthead/bandnav/pressbar），五个编辑部页面（前厅/编目室/通稿审核/清样/校对室）已按此范式落地；`design/UI_UX_CONTRACT.md` 视觉条款（tabular-nums、1px 分层、4px 网格、状态带文字）继续有效。
3. **现行 token 成熟**：冷白/深海军蓝/暖米黄三态 + mint/amber/red 语义三色锁 + 零阴影 hairline 纪律——重构延续而非推翻。
4. **技能路由**：`redesign-existing-projects`（Tier 1.2 现有项目改造）要求与既有栈协作、小步可审；`industrial-brutalist-ui` 提供瑞士印刷网格 + 军事遥测的参照语汇（取其网格与密度，不取纯黑 CRT 与 0 圆角——与现行 6/8/10 圆角和三态主题冲突）。

**不采用**：暗色 CRT 独占、营销风/休闲风、新一级入口/新壳（壳冻结 C-1 硬约束）、emoji 图标（契约禁令）。

## 2. Token 契约（唯一真相源，三态同构）

| token | light 冷白 | dark 深海军 | paper 暖米黄 |
| --- | --- | --- | --- |
| `--bg` / `--card` / `--hover` | `#edf1f7` / `#ffffff` / `#e2e9f3` | `#0a1628` / `#0f2140` / `#13294d` | `#F7F4EE` / `#fdf8ec` / `#f5f0e6` |
| `--ink` / `--ink-2` / `--ink-3` | `#14294a` / `#45597c` / `#7188a8` | `#eef3fa` / `#9db0c9` / `#5f7492` | `#1C1917` / `#5a4a36` / `#8a7659` |
| `--line` / `--line-strong` | `rgba(22,43,80,.13)` / `.28` | `rgba(148,180,220,.14)` / `.30` | `#E4DED2` / `#cfc6b4` |
| `--accent` = `--mint` | `#04785c` | `#00e5a0` | `#BE3426`（编辑红）/ mint `#2E6B4F` |
| `--amber`（需注意/写操作） | `#a86314` | `#ffab5e` | `#A0691F` |
| `--red`（**仅漏洞告警**） | `#cc3d50` | `#ff6470` | `#BE3426` |
| `--info` | `#0e7490` | `#4dd6e2` | `#3B5B78` |

- **字体**：正文 mono 13px/1.65（JetBrains Mono 栈）；壳 sans 15px（Inter 栈）；报头/纸质主题衬线（Source Han Serif SC 栈）。**数字一律 `.num`（tabular-nums）**。
- **语义三色锁**（三态通用）：mint=正常/新增/激活 · amber=需注意/写操作橙标 · red=仅漏洞告警。**状态必须带文字 label，不只靠颜色**。
- **密度**：表格行 44px、工具栏 40–44px、输入框 32px；间距 4/8/12/16/20/24/32/40（4px 网格）；圆角 6/8/10 三档。
- **零阴影纪律**：层次只靠 hairline 与 1–3% 亮度差；动效 120/200/320ms `cubic-bezier(0.16,1,0.3,1)`，尊重 `prefers-reduced-motion`；正文下限 11px。
- **对比度**：普通文字 ≥4.5:1；paper 墨色 11.7:1。

## 3. 组件词汇表（全站统一，demo 内已全部实现）

| 组件 | 用途 | demo 类名 |
| --- | --- | --- |
| 壳三段 | 报头（品牌+四菜单+命令栏+主题+时钟）/ 版面条 chips / 印务条心跳 | `.sn-mast` `.sn-nav` `.cmd` `.sn-band` `.chip` `.sn-press` `.pipe-block` `.beat-lights` `.pulse` |
| 状态徽章 | ✅ 已上线 / ◐ 部分就绪 / ○ 未实现（虚线）/ ◈ 纪律生效 / ↷ 重定向 | `.badge .b-ok/.b-part/.b-none/.b-disc` |
| **未实现印章** | ○/◐ + 能力号 + 一句话 + PRD 依据 + demo 落点 | `.stamp .st-mark/.st-t/.st-d/.st-e` |
| 数据表 | 粘性表头、44px 行、数字右对齐、hover 仅背景 | `.tbl` |
| 空状态四态 | loading（骨架）/ empty / stale（含最后成功时间）/ error（显式+重试） | `.empty4` |
| 资讯卡 | sev 色条 + 来源/时间/pick + 赞/踩/收藏（状态型互斥） | `.feed-card` `.sev` `.react` `.hint-chip` |
| 四段指挥台 | 信号立案 → 案件研判 → Run 人工回执 → 产物沉淀 | `.console .stage .stage-item` |
| 提案卡 | 类型章/发起方/证据数/两步批准/驳回必填 | `.prop .pr-type .confirm-inline` |
| 案件页签 | overview/evidence/judgments/actions/artifacts/review | `.case-tabs` `.evidence-ref` `.guard-box` |
| 页面档案 | 目标形态 wireframe + 状态/API/依据（未接富视图的页） | `.wireframe .wf-zone` |
| 指标瓦片 | 大号 tabular-nums + 口径注 | `.statTile`（statTile 函数） |
| 无限画布 | 拖拽平移 / ctrl⌘+滚轮光标锚定缩放 / 双击重置 / 点阵网格 | `canvas.html` |

## 4. 完整覆盖核对（不得遗漏的证据）

### 4.1 路由覆盖 —— 60/60

- **44 条页面路由全部入 demo**（✅ 组件实测存在）：资讯 7 / 知识 23 / 行动 5 / 设置 8 / 无菜单 1。
- **12 个富视图**（完整交互）：`/`、`/action`、`/cases/:caseId`、`/knowledge`、`/knowledge/khub`、`/knowledge/graph`、`/settings`、`/quality`、`/secnews/pipeline`、`/maint`、`/skill-store`、`/reader/:id`。
- **31 个档案视图**（统一风格 wireframe + 功能/API/依据 + 未实现印章）+ 1 个 demo 辅助页（`#/coverage` 覆盖地图）。
- **16 条重定向**全部演示真实跳转（含 1.4s 自动跳 + 手动按钮），零死链；`*` 兜底同样演示。
- **3 条 gate 条件路由**（`/sync` `/codegarden` `/codegarden/phase2b`）：gate 关闭时渲染 404 形态说明卡，可在设置页开合体验。
- **QA 实测**：43 个页面路径 + coverage 全部渲染，**0 JS 错误**（浏览器实测 2026-11-17）。

### 4.2 PRD 能力覆盖 —— 92/92（明细见 demo `#/coverage`）

| 状态 | 数量 | demo 呈现方式 |
| --- | --- | --- |
| ✅ 已上线 | 61 | 页面正常呈现 + 徽章标注能力号 |
| ◐ 部分就绪（含 4 个后端就绪前端未接的 API 域） | 19 | 页内 ◐ 印章（缺什么/依据） |
| ○ 未实现·规划 | 7 | 页内 ○ 虚线印章 + 画布缺口卡（DATA-8/10、KNOW-13、ACT-14/15/17、XF-25）+ MP-3/MP-4（图谱页） |
| ◈ 纪律生效（明确不做/持续有效） | 5 | 覆盖地图标注（SET-15、XF-13/20/21/23） |

- 未实现项的标记格式统一：**印章 = 状态符 + 能力号 + 需求一句话 + PRD 出处 + demo 落点**；前端不展示伪造数据（与仓库 UNIMPLEMENTED 台账原则一致）。
- 30 天观测窗（ACT-18/19）：行动页 KPI 瓦片与设置运维区如实标「观测中，不宣称达标」。

### 4.3 业务流贯通（用户操作路径完整性）

1. **主链**：资讯流 → 建案提案（人确认）→ 案件工作区六节 → AI 起草研判（proposal→审批收件箱两步批准）→ Run 人工回执四态机（CAS/409）→ Artifact 验收（sha256）→ SK-04 复盘回流 → 知识发布/复查/采用。
2. **告警流**：告警 tab（action_hint 徽标）→ 信号 → 案件 → 处置。
3. **治理流**：设置 7 cat → 16 gate 开合（实时影响版面条与路由可见性）→ 失败面板/拒收日志人话化。
4. **命令流**：CommandBar 四类意图模板，不可识别显式列出（不猜），执行类诚实 unsupported。
5. **复核流**：校对室门禁统计 → 规则两层 → 拒收回放；管线观测漏斗 → 16 源灯。

## 5. 落地路线（接入 frontend/src 的建议批次，均不违反壳冻结）

| 批次 | 内容 | 影响面 | 验收 |
| --- | --- | --- | --- |
| **R-1 token 对齐** | 工具页散落的字面值颜色/圆角收敛到 `index.css` 现有变量（本契约未新增变量，仅归一） | `tailwind.config.js` + 少量 css | `tsc --noEmit` + 全量 vitest + 三主题走查（顺带闭 T8） |
| **R-2 组件词汇表替换** | StatusBadge/DataTable/空态四态按 §3 统一替换各域实现（先 grep 复用，禁止平行新增） | `components/**` 逐域小步 PR | colocated 测试 + `nav4_shell.test.tsx` |
| **R-3 印章组件化** | 未实现印章做成共享组件（数据源 = PRD 能力清单常量），替换现有散落占位 | `shared/editorial/` | 覆盖地图页核对 92 条 |
| **R-4 心跳条/命令栏微调** | pressbar 漏斗段宽与 16 灯状态语义对齐；CommandBar 意图模板文案对齐 PRD | `SentinelShell.tsx` | 壳守卫测试不破 |

- 每批独立 commit + DEV_LOG；架构数字若涉及注册代码变更须同步 `generate_meta.py --fix`。
- **红线不动**：`gateway._try_order`/`_resolve_provider`；四菜单壳；`sentinel.css` (0,0,1) 特异度与 border 非简写。

## 6. 边界与不做

- 本 demo 是**重构蓝本**，不是生产代码：不接真实 API、不落库；一切写操作只给「演示」反馈，不伪造成功（人主律在 demo 中同样成立）。
- 演示条目内容（资讯/案件/提案等）为演示样例并全站标注；真实底数（架构数字、KPI、gate 清单、观测窗）取自 PRD/审计公开口径。
- 不新增一级入口/新壳/第二导航；`#/coverage` 为 demo 辅助页并明确标注，非产品路由。

---

## 7. 委托对账与证据边界（reconciliation）

本任务委派了三个研究员子任务（2026-11-17）：**全部 completed，回执可用（0 失败 / 0 停止 / 0 空回执），无需要重做的范围**。产出均已全文读取并消费进交付物：

| 子任务 | 产出文件 | 消费落点 |
| --- | --- | --- |
| 全站路由与实现状态盘点 | `design/_research/routes-status.md` | `registry.js` 44 页面路由 + 16 重定向 + 4 个 ◐ API 域 + 16 gate；`#/coverage` 路由表 |
| PRD 能力/需求清单 | `design/_research/prd-capabilities.md` | `registry.js` CAPS 92 条 + 页内 ○/◐ 印章 + 覆盖地图状态分布（61/19/7/5） |
| 前端视觉系统盘点 | `design/_research/frontend-visual.md` | `style.css` 三态 token 实测值（hex 逐一取自该盘点）、壳三段结构（masthead/bandnav/pressbar、16 源灯 DEV-0194、menuOf 口径） |

**继承的证据边界**（子任务如实声明的待证项，非失败；demo 未将其当作已证事实）：

1. PRD 能力状态为 **PRD 文本层转述，未做逐条代码核验**——demo 印章均标注 PRD 出处而非代码验证，覆盖地图页注明数据源口径。
2. `ReportPage` / `KnowledgeCompile` / `KnowledgeCompound` / `ObservabilityTab` 的 API 消费只证到**子组件文件级**——demo 中这四页的 api 字段如实标「子组件：…」。
3. `generate_meta.py --check` 与 `_registry.py` 计数核对未跑——demo 使用 ARCHITECTURE.md 门禁口径数字（99 routers / 155 services / 56 jobs / 19 collectors），未自行重新统计。
4. AgentFeed MCP 本运行时未挂载（`.mcp.json` 仅 gortex），开工步 `getContext` 未执行——证据源改为一手代码与文档，已在任务收尾如实说明。

**验证与实现分离**：demo 的 QA（44 路由浏览器实测 0 JS 错误、demo 链接零死链、覆盖脚本核对 92 条）由主 agent 独立执行，与产出 demo 的实现侧分离。

---

## 附：demo 运行方式

`design/redesign-v1/` 目录下**双击 `index.html`**（file:// 直开，纯静态零依赖）；`canvas.html` 同目录双击或从页脚/图谱页进入。建议 ≥1280 宽视口；三态主题在报头「◐ 主题」或设置页切换。
