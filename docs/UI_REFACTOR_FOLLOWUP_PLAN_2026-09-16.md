# UI 重构收尾批 — 未实现与增强项方案设计

> **时间**: 2026-09-16 · **编号**: DEV-0185 · **性质**: 方案设计（本文档不含代码变更）
> **上游**: 全系统 UI 重构五阶段 (DEV-0180~0184) 的全部未实现项、需补充考虑项、增强项
> **权威约束**: 四菜单唯一壳不破（`frontend/src/AGENTS.md` 硬规则）；单一权威 PRD `docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md`；实现与验证分离
>
> **两处事实修正**（本设计核查代码后推翻 Phase 4 台账假设，已同步回写 `docs/UNIMPLEMENTED.md`）:
> 1. **编目室不缺后端**——`GET /api/knowledge/items` 已存在（`backend/api/knowledge_items.py:19`），支持 domain/source/type/difficulty/compiled/时间窗 + limit/offset 全维度筛选分页；`knowledge_items` 表（migration 018）本就是 wiki md 的编目镜像（id/title/source/domain/type/difficulty/mastery/ingested_at）。无需 migration 118。
> 2. **批注表已存在**——`annotations` 表（migration 027，含 `range_start/range_end` 列）+ `AnnotationsRepo`（create/list_by_entity/delete/count）均已落地，仅缺一个薄 API router。无需任何 migration。

---

## 0. 批次总览与优先级

| 批次 | 内容 | 工期 | 性质 |
|---|---|---|---|
| **A 快赢修整** | 8 项前端小修（sticky 层叠 / events 确认 / 滚轮开关 / hit-area / query 透传 / 动态 bounds / bandnav 收起 / 字号） | 1–1.5 天 | P0×2 + P1×6 — ✅ 已交付 (DEV-0188, 2026-09-16; A7 收起态实现为 24px 单按钮条, 替代原设想的 4px 热区) |
| **B 页面编辑化收尾** | Phase 3 顺延页（SettingsPage / pipeline 矩阵 / analytics / review / skills / garden / reports） | 2–3 天 | P1 — ✅ 已交付 (DEV-0192; B1 mixed 版式 / B2 源矩阵 / B3 StatCard / B4 garden 覆盖块 / B5 review+skills+reports 走 opt-in ed-typo 衬线类——Tailwind token 页不做侵入式手术, 同 CaseDetail 先例) |
| **C 后端缺口落地 + 前端接线** | C1 编目室接真实数据（**0 后端**）✅ 已交付 (DEV-0189) / C2 批注 B+ 锚点 ✅ 已交付 (DEV-0190, API 实为已存在仅扩展 quote) / C3 hub-stats 聚合 ✅ 已交付 (DEV-0191, 挂既有 router 计数不变) | **C 批全部完成** | P1（C1 可单独先行，0.5 天） |
| **D 裁决与依赖项** | 字体策略 / events 写库策略 / storage 豁免口径 / CaseDetail 稿签化 / 实机走查 | 裁决驱动 | 需 owner 拍板 |

执行顺序建议：**A → C1 → C2 → C3 → B → D**（C1 是全计划杠杆最高项：0 后端改动让编目室从占位变真实数据）。

---

## 1. 批次 A：快赢修整

### A1（P0）首页双 sticky 条层叠透出
- **问题**: 首页第二条检索 controlbar `sticky top:52` 与 bandnav（`sticky top:0`，高约 33px）滚动时重叠，controlbar 半透明底（`rgba(10,22,40,.92)` 类）透出 bandnav 边线。
- **方案**: sentinel.css 引入 `--sn-bandnav-h: 33px`；`.controlbar { top: var(--sn-bandnav-h) }`；第二条检索条 `top: calc(var(--sn-bandnav-h) + 52px)`；controlbar 背景从半透明改实底 `var(--sn-bg)`（三主题各自 token 已定义，blur 保留）。
- **改动面**: 仅 `sentinel.css`（~5 行）。
- **验收**: 浏览器滚动至检索条吸顶，bandnav 与其边界无透叠；暗/亮/paper 三主题目检。

### A2（P0）通稿审核批量通过两段式确认
- **问题**: batch-approve 直接写生产库 + audit_log_mp2_review，一次误点影响面大。
- **方案**: 前端两段式 armed 确认——首次点击进入待确认态（按钮文案变「确认批量通过 (≥0.7)?」、amber 描边，5 秒无操作自动退出）；二次点击才发 POST。单条 approve/reject 保持即时（驳回有理由必填门禁 + 全量审计可对冲）。**不引入全局 dry-run 开关**（后端语义已定，UI 层守卫够用且不动 API）。
- **改动面**: `EventsReviewPage.tsx`（armed state + 定时器）+ 测试 1 用例。
- **验收**: vitest 断言首次点击不发请求、armed 文案出现、超时回退；二次点击请求发出。
- **风险**: 与 owner 若裁决要更强守卫（服务端 dry-run），此 UI 方案不冲突，可叠加。

### A3（P1）InfiniteCanvas 滚轮接管开关
- **问题**: 光标停在画布上滚动页面，先触发画布缩放（preventDefault），嵌入页滚动被劫持。
- **方案**: `InfiniteCanvas` 加 prop `zoomOnWheel: 'always' | 'modifier'`，默认 `'always'`（保持原型语义）；`'modifier'` 模式下纯滚轮不 preventDefault（页面正常滚动），仅 ctrl/⌘+滚轮缩放。graph 与 kcanvas 先保持默认，实机走查后按反馈切换。
- **改动面**: `InfiniteCanvas.tsx` onWheel 分支（~10 行）+ 测试 1 用例。
- **验收**: modifier 模式下纯 wheel 事件不调用 preventDefault（jsdom 可断言 `defaultPrevented === false`）。

### A4（P1）graph 画布模式极小 zoom 命中补偿
- **问题**: 画布模式 SVG 固定 760×520，zoom < 30% 时节点点选困难。
- **方案**: 画布模式下每个节点 `<g>` 内前置一个透明命中圆 `<circle r={max(n.r, 14/zoom)} fill="transparent" pointer-events="all">`（zoom 感知，视觉零变化，仅放大热区）。
- **改动面**: `SentinelGraphPage.tsx` 节点渲染分支（~4 行）。
- **验收**: 现有 graph 12 用例零回归（命中圆 aria-hidden）。

### A5（P1）/quality/rejection 重定向 query 透传
- **问题**: 现 `<Navigate to="/quality?tab=rejection">` 丢弃原 URL 其他 query。
- **方案**: 换成已有的 `QueryRedirect` 变体——合并 query：`to={`/quality?tab=rejection${search ? '&' + search.slice(1) : ''}`}`（routes/index.tsx 内联小组件或扩展 QueryRedirect 支持附加 query）。
- **改动面**: `routes/index.tsx`（~8 行）。
- **验收**: `/quality/rejection?foo=1` → `/quality?tab=rejection&foo=1`（MemoryRouter 断言）。

### A6（P1）kcanvas 边层动态 bounds
- **问题**: 边层 SVG 尺寸写死 1400×800，节点拖出域后边不绘制。
- **方案**: `useMemo` 从 positions 计算 `width = maxX + 200 / height = maxY + 200` 动态传入 SVG；world 尺寸同步取 `max(1400, width)`。
- **改动面**: `KnowledgeCanvasPage.tsx`（~6 行）。
- **验收**: 拖节点至 (1600, 900) 后边仍绘制（jsdom 断言 svg width 属性 ≥ 1800）。

### A7（P1）bandnav 收起开关
- **问题**: bandnav 使壳常驻 +33px，深读场景挤占纵向空间。
- **方案**: bandnav 右端加收起按钮（chevron 图标），收起态 `localStorage 'bandnav-collapsed'` 持久化、条高 0（`display:none`）+ 在 masthead 下沿露出一条 4px 悬停热区可再展开；A1 的 `--sn-bandnav-h` 随之切 0。
- **改动面**: `SentinelShell.tsx`（state + 按钮）+ `sentinel.css` + 测试 1 用例。
- **验收**: 收起后刷新保持；controlbar sticky 偏移同步归位（A1 的 var 联动）。

### A8（P1）pressbar 数值字号回 14px
- **问题**: Phase 2 单行化时 pipe-v 从 15px 降到 13px，密度偏高。
- **方案**: `.sentinel .pipe-v{font-size:14px}`（一行）。**属裁决项**——owner 若认可 13px 则关闭此项。

---

## 2. 批次 B：页面编辑化收尾（Phase 3 顺延页）

统一手法沿用 Phase 3 已验证的「CSS 覆盖块 + 共享 .ed-* 类」路线（DOM/数据流不动，测试零回归）。

### B1 SettingsPage 版面重排（社务处）
- **现状**: `.settings-shell` + 210px sidenav + 17 分类面板纵向堆叠；原型是「左分类 + 右 5 列卡网格 `.st-grid5`」。
- **方案**: **保留 sidenav**（17 类需纵向导航，与原型左栏职责等价），分类面板按内容形态分三类布局——
  - `grid`（体检面板/能力开关/图片模型等卡片型）：容器换 `.ed-grid`（`auto-fill minmax(230px,1fr)`，1580px 容器下自然 5 列）
  - `form`（采集间隔/管道配置等表单型）：保持全宽
  - `mixed`：上统计卡 grid + 下表单全宽
  - 形态由 `cat → layout hint` 常量表声明（17 类逐一定档），面板内容零改动
- **改动面**: `SettingsPage.tsx`（hint 表 + 容器类）+ `pages.css`（.ed-grid 已有，复用）。
- **验收**: 现有 SettingsDashboard/设置页测试零回归；1580px 视口 grid 类目呈现 ≥4 列。

### B2 pipeline 源矩阵表（印厂调度）
- **方案**: 新增 `SourceMatrixCard`：`.ed-table` 渲染 `/api/sources/health`（壳心跳同源接口，无新端点），列 = 源 / 类目 / 状态（--ok/--warn/--err 着色）/ 累计条目 / 最近活动；置于 FunnelBar 之下。排序：dead → stale → active。
- **改动面**: 新组件 + `PipelineView.tsx` 挂载 + colocated test。
- **验收**: 101 源分页或虚拟化不卡（>100 行时 limit 100 + 计数提示）；表格行 hover 走 ed-table 既有样式。

### B3 analytics 统计卡（发行统计）
- **方案**: 从 `.ed-card` 抽共享 `StatCard`（k/v/d 插槽，Phase 4 khub 已用同构 markup），analytics 顶部统计区换 StatCard 网格；图表区不动。
- **改动面**: `shared/editorial/StatCard.tsx`（新，~40 行）+ `SecNewsAnalytics.tsx` 顶部区替换 + 测试。

### B4/B5 P2/P3 四页（review / skills / garden / reports）
- **方案**: 每页一档「编辑部排版覆盖块」（衬线标题 + ed-sechead + ed-btn/ed-table 吸收），与 Phase 3 sentinel-action.css 覆盖块同模式：
  - **review（间隔复习）**: 复习卡 + 评分按钮组对齐原型 `.grade-btn`（hairline 按钮已有 ed-btn 同语言）；衬线卡片题
  - **skills（专栏作家库）**: 技能卡网格换 `.ed-grid` + 卡题衬线；矩阵表换 ed-table
  - **garden（副刊工坊）**: sentinel-garden.css 追加覆盖块（泳道标题衬线 + 服务卡 ed-card 化）
  - **reports（成品间）**: 报告卡 ed-card 化 + 预览区 ed-reader 排版复用
- **改动面**: 每页 CSS 覆盖块 + 少量容器类；预计每页 0.5 天、零 DOM 重构。
- **验收**: 各页现有测试零回归 + 每页 1 个「衬线标题存在」类目检用例。

---

## 3. 批次 C：后端缺口落地 + 前端接线

### C1（最高杠杆，0 后端）编目室接真实数据
- **事实**: `GET /api/knowledge/items`（`knowledge_items.py:19`）已提供 items + total，筛选 domain/source/type/difficulty/compiled/since/until + limit/offset；`knowledge_items` 表列覆盖计划表头 6 列中的 5 列——条目标识=id、标题=title、领域=domain、来源=source、收录时间=ingested_at；**复习状态用已有 `mastery` 列**（0–5 掌握度，SM-2 的库内代理）呈现。
- **方案**:
  - `KnowledgeLibraryPage` 摘除占位（空态/印章/自检按钮），接 `GET /api/knowledge/items`；
  - 筛选条: 领域（`/api/knowledge/topics` 取 distinct）/ 来源 / 类型 / 难度 + 翻页（limit 50）；
  - 关键词搜索**不在此页做**（该端点未暴露 repo 的 keyword 参数；全文检索已有 `/search` 与 `/api/wiki/search` 承载，避免端点扩权）；
  - 同 commit 更新 `UNIMPLEMENTED.md` 条目 2 → 已实现（口径注明「编目 = knowledge_items 镜像」）。
- **改动面**: 纯前端 + 测试改写（fixture 用真实响应形状）。
- **工期**: 0.5 天。**建议第一批做**。

### C2 批注薄 API + reader 接线
- **事实**: `annotations` 表（migration 027: entity_type/entity_id/content/**range_start/range_end**/时间戳 + entity 索引）与 `AnnotationsRepo`（create/list_by_entity/delete/count）已在；缺 HTTP 层。
- **方案**:
  - **后端**: `backend/api/annotations_api.py` 薄 router（≤80 行）：
    - `GET /api/annotations?entity_type=&entity_id=`
    - `POST /api/annotations` `{entity_type, entity_id, content, quote, range_start?, range_end?}`（quote = 高亮原文引文, 上限 500 字）
    - `DELETE /api/annotations/{id}`
    - 写操作 record_audit；复用 repo，零新 service
  - **migration 118**（B+ 定稿）: `ALTER TABLE annotations ADD COLUMN quote TEXT`（3 行, 加列向后兼容; 旧行 NULL 降级为纯偏移行为）
  - **锚点约定（B+）**: `entity_type='wiki_item'`，`entity_id=<条目 id>`，`quote`+`range_start/end` = 高亮原文 + 正文字符偏移；渲染时四步解析（快路径校验 → 窗内重锚自愈 → 全文兜底 → 标 stale），详见 C2.1
  - **wiki-first 合规**: 批注是阅读层元数据，**不写 wiki md**——单写路径（write_item_to_md/ai_write_back）不动，与 reviews 队列同属 DB 侧车数据模式
  - **前端**: `DeepReaderPage` 选中文字 → 浮动「批注」按钮 → textarea → POST；右栏批注列表三态（定位/迁移/未定位）+ 点击滚动定位 + 删除；渲染器暴露 raw 偏移→渲染位置映射（画高亮固有成本）；摘除「批注能力未实现」印章
- **改动面**: 后端 1 文件 + migration 118 + 测试（CRUD×3 + audit 断言）；前端 reader 接线 + 偏移映射 + 测试改写。
- **工期**: 1–1.5 天。

### C2.1 锚点抗漂移设计（2026-09-16 补充；✅ 同日 owner 拍板按 B+ 定稿）

**漂移机理**: 原 C2 锚点 = 纯字符偏移（`content.slice(start, end)`）。wiki-first 下条目 md 是活文档——重采集去重失败、编译回写、AI write-back 都会经 `write_item_to_md` 重写正文；任何在批注位置**之前**的增删都会平移偏移量。两类失败：①**静默错锚**（偏移仍落在文内，但指向别的句子——批注像在批评一段它没批评过的话，安全工作流里这是最危险态）；②**越界失锚**（文档变短，前端只能钳制或丢弃）。

**取舍空间**（已评估五个档位）:

| 方案 | 抗漂移 | 成本 | 判定 |
|---|---|---|---|
| A 纯偏移（原 C2） | 无 | 0 | ❌ 静默错锚不可接受 |
| **B+ 引文 + 偏移提示自愈** | 抗上游增删 | +1 列 + ~40 行解析 | ✅ **推荐** |
| C 完整 TextQuoteSelector（引文+前后缀+模糊匹配, W3C 模型） | 更强（消歧重复） | +3 列 + ~80 行 | 首版过重, 可后升（加列即可, 不破坏 schema） |
| D 结构锚（标题相对定位） | 最强 | 重实现 | 过度设计 |
| E 版本快照（内容 hash 绑定） | 无漂移但全灭 | wiki 单写路径下任何改写都换 hash → 全部批注变 stale | ❌ 与活文档哲学冲突 |

**B+ 设计**:
- 存储: `ALTER TABLE annotations ADD COLUMN quote TEXT`（migration 118, 3 行; 旧行 quote=NULL 自动降级为 A 方案行为, 向后兼容）。
- 解析（渲染时, 纯前端 ~40 行）: ①快路径 `slice(start,end)===quote` → 定位；②失配 → 在原偏移 ±2000 字符窗内搜引文, 取最近出现 → **重锚定**（可选回写新偏移, 自愈）；③全文搜引文取最近；④找不到 → 标 `stale`, 右栏「未定位」展示, **永不静默错放**。
- UI 三态: 定位（绿点）/ 迁移（蓝点, 已重锚）/ 未定位（灰点, 仅右栏）。
- 成本变化: C2 从「0 migration」变「+1 个 3 行 ALTER migration」；另 reader 渲染器需暴露 raw 偏移→渲染位置映射以画高亮（+~50 行, 本就属于高亮功能的实现成本）。

### C3 hub-stats 聚合端点
- **方案**: `GET /api/knowledge/hub-stats`（只读，无 gate）→ `backend/services/hub_stats_service.py` 聚合既有数据源：
  ```json
  { "wiki_items": <knowledge_repo.count_items()>,
    "wiki_chunks": <chunks 表 count>,
    "review_due": <reviews /stats 同源查询>,
    "funnel_total": <kl pipeline stats 漏斗合计>,
    "queue_pending": <同上>,
    "quality_checked_24h": <quality summary 合计>,
    "generated_at": "<iso>" }
  ```
  - 不新建表、不落缓存（全只读聚合，单请求 <50ms 量级）；router 挂 `_registry.py` 并同步 `generate_meta`（routers +1）
  - **khub 同 commit 切换**: 派生卡换真值、摘 `hub-stats 未实现` 印章与 TODO、`UNIMPLEMENTED.md` 条目 1 → 已实现（A9 预案兑现）
- **改动面**: service + router + registry + ARCHITECTURE 数字 + 测试（聚合正确性 / 空 DB / 端点形状）。
- **工期**: 0.5–1 天。

---

## 4. 批次 D：裁决与依赖项（不排期，待 owner）

| # | 项 | 选项与建议 | 裁决 |
|---|---|---|---|
| D1 | **衬线 900 字重退化** | (i) 自托管 `@fontsource/noto-serif-sc` 可变字重（~2–4MB，本地工具可接受，paper 主题懒加载）；(ii) 先降 900→700 避免合成加粗（一行 CSS）。**建议 ii 先行、i 作为正式方案**，实机看效果后定 | ✅ 2026-09-16 owner：**不需要调整**（维持 900，不自托管字体，此项关闭） |
| D2 | **events 写库策略** | 本设计 A2 已给 UI 两段式守卫；若需服务端 dry-run（预览将通过的候选清单不落库）为独立后端小项（~0.5 天），待裁决 | ✅ 2026-09-16 owner：**按建议执行**（仅 UI 两段式确认 A2，不做服务端 dry-run，此项关闭） |
| D3 | **设置页 storage 豁免口径** | 维持现状（生产 routes 层本就每页写 gate 布尔缓存，非敏感）；**不建议**为此给 useFeatureFlags 加 persist 开关（为测试改生产代码） |
| D4 | **CaseDetail 稿签化** | 阻塞于 v1 panels 激活（v1_runs/v1_artifacts 代码级死锁，见 `docs/audit/PRD_ALIGNMENT_AUDIT_2026-09-14.md`）；P1-0 落地后按 Phase 3 模式换 Ticket/Stamp，届时单独立项 |
| D5 | **实机视觉走查** | 五阶段交付均未做浏览器验收；建议清单：paper 主题下 报头/首页头条/行动层/通稿审核/清样深读/两个画布 + A1 修复后 sticky 滚动 + A3 两模式滚轮手感 |

---

## 5. 设计决策记录（关键取舍）

| # | 决策 | 理由 |
|---|---|---|
| DD-1 | 编目室复用 `/api/knowledge/items`，**不建 knowledge_library 表** | knowledge_items 本就是 wiki 镜像的编目事实源；建平行表违反 wiki-first（双真相源漂移），且端点已在 |
| DD-2 | 批注复用 migration 027 表，`entity_type='wiki_item'`，**不写 md** | 阅读层元数据与 SM-2 复习队列同属 DB 侧车；保持 wiki 单写路径不被侵蚀 |
| DD-3 | events 守卫用 UI 两段式而非服务端 dry-run | 最小改动面覆盖主要误伤路径（批量）；审计日志已是完整对账面 |
| DD-4 | 编目页不做关键词搜索 | 该端点未暴露 keyword（repo 有但 API 无）；全文检索已由 /search 承载，避免为单一页面扩端点权限 |
| DD-5 | `zoomOnWheel` 默认 `'always'` | 保持方案B 原型语义；切换由实机反馈驱动而非预设 |
| DD-6 | hub-stats 不落缓存表 | 全只读聚合 + 低频访问（前厅一次）；缓存表会引入失效问题 |
| DD-7 | 批注锚点定稿 **B+**（引文 + 偏移提示自愈；migration 118 加 quote 列） | owner 2026-09-16 拍板：3 行 ALTER 换掉唯一的静默错锚失败模式；旧行 NULL 向后兼容，日后可无破坏升 C 档（TextQuoteSelector） |

## 6. 验收矩阵与排期

| 批次 | 门禁 | 交付判据 |
|---|---|---|
| A | vitest + tsc + build 全绿 | A1/A2/A3 各 1 新用例；其余目检项列入 D5 走查单 |
| B | 同上 + 各页测试零回归 | 每页衬线化目检用例 1 个 |
| C | 同上 + **pytest 全绿** + generate_meta 同步（C2 +migration 118 / C3 routers +1） | C1/C2/C3 各自 UNIMPLEMENTED.md 条目闭环 |
| 总 | 五件套门禁（tsc/vitest/build/pytest/meta） | DEV_LOG 逐批记录（DEV-0186 起） |

**总计约 5.5–7.5 个工作日**（A 1.5 + C 2.5 + B 3 + D 裁决驱动），每批独立可交付可回滚。

## 7. 不做清单（明确出界）

- 不为编目/批注新建任何数据表（DD-1/DD-2）；唯一 schema 变更为 migration 118 的 `ALTER ADD quote` 列（B+, DD-7, 已批）
- 不动 ai_hub 调用链、feature gate 语义、四菜单壳结构
- 不在批次内引入新 npm 依赖（字体自托管属 D1 裁决后单独批）
- 触控板 deltaX 判据保持原型值（A13 并入 D5 走查观察项，反馈后再定）
