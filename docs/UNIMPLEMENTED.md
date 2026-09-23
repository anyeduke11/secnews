# UNIMPLEMENTED — 未实现功能台账

> **状态 (2026-09-16, C3/DEV-0191)**: ✅ **Phase 4 五视图的未实现项已全部闭环** — khub/library/events/reader/quality 五页均为真实数据, 无占位残留。本台账保留为历史记录与口径档案; 后续新增占位功能时在此登记。
> 原则: 前端"有壳有占位", 未实现的后端端点在代码内以 `// TODO: [DEV-XXXX] backend not implemented: <endpoint>` 登记, 页面上以「印章 + 空态」显式告知, **不展示伪造数据**。
> 关联: 单一权威 PRD `docs/HOTSPOT_SECURITY_AI_WORKBENCH_PRD.md`; 收尾批方案 `docs/UI_REFACTOR_FOLLOWUP_PLAN_2026-09-16.md`。

## 总览

| # | 视图 | 路由 | 缺失端点 | 状态 | 前端处理 |
|---|------|------|----------|------|----------|
| 1 | 资料库前厅 khub | `/knowledge/khub` | 无 — `GET /api/knowledge/hub-stats` 已落地 (C3) | **已实现 (真实数据, C3/DEV-0191)** | 六源聚合统计卡 (编目/chunks/复习/漏斗/队列/门禁) + 逐源容错 (失败源显示 …) |
| 2 | 编目室 library | `/knowledge/library` | 无 — 复用既有 `GET /api/knowledge/items` | **已实现 (真实数据, C1/DEV-0189)** | 领域/主题/类型/难度筛选 + 翻页 + 掌握度列 (SM-2 库内代理); 不建平行表 (wiki-first) |
| 3 | 通稿审核 events | `/action/events` | 无 — 端点全部存在 | **已实现 (真实数据)** | `GET/POST /api/event-technique/*` 六端点全接: 类型进度 / 候选队列 / 通过 / 驳回(理由必填) / 批量通过 |
| 4 | 清样深读 reader | `/reader/:id` | 无 — API 已存在 (v1.7 Phase 2), 既有表加 quote 列 (migration 118) | **已实现 (真实数据, C2/DEV-0190)** | 正文 + 批注全真实: B+ 四步抗漂移解析 / mark 高亮 / 选区批注 / 侧栏三态; 不写 wiki md |
| 5 | 校对室 quality | `/quality` | 无 — 原型设想的 rules 端点已存在 | **已实现 (真实数据)** | `GET /api/quality/summary` 门禁卡 + `GET /api/info-filter/rules` 规则表 + 拒绝样本子标签 (旧 `/quality/rejection` 重定向兼容) |

## 明细

### 1. hub-stats 聚合端点 — ✅ 已闭环 (C3, DEV-0191)

- **落地方式**: `backend/services/hub_stats_service.py` 聚合六源 (knowledge_repo.count_items / knowledge_chunks COUNT / review_service.stats / wiki_stats_service.funnel_from_db / kl 队列 / QualityLogRepository.summary_24h), 逐源容错 (单源失败置 None, 前端显示 …); 端点挂既有 `knowledge_api.py` 聚合 router (`GET /api/knowledge/hub-stats`), routers 计数不变, services 145→146 已同步。
- **不落缓存** (DD-6): 全只读聚合, 单请求直算。
- **代码位置**: `backend/services/hub_stats_service.py` + `frontend/src/components/knowledge/KnowledgeHubPage.tsx`

### 2. 编目室清单端点 — ✅ 已闭环 (C1, DEV-0189)

- **落地方式**: 零后端——前端接既有 `GET /api/knowledge/items` (`backend/api/knowledge_items.py:19`, domain/topic/type/difficulty 筛选 + limit/offset 分页); `knowledge_items` 表 (migration 018) 即编目事实源, **不建 knowledge_library 表** (wiki-first: DB 镜像即编目, 避免双真相源)。
- **已交付**: 领域/主题 (随领域联动 `/api/knowledge/topics`)/类型/难度四维筛选 + 翻页 (50/页, hasNext 以本页条数判定); 掌握度列 = `mastery` (SM-2 库内代理); 页脚如实标注 total 为「域口径」(后端 count 仅按 domain)。
- **已知口径**: 关键词搜索不在本页 (DD-4, 由 /search 与 /api/wiki/search 承载)。
- **代码位置**: `frontend/src/components/knowledge/KnowledgeLibraryPage.tsx`

### 3. (无缺口) 通稿审核

MP-2 已交付 `/api/event-technique` 六端点 (migration 117, `event_technique_api.py` + `event_types_api.py`), 前端本批全量接入。approve/reject/batch-approve 均写 `audit_log_mp2_review` (actor=owner)。

### 4. reader 批注能力 — ✅ 已闭环 (C2, DEV-0190)

- **落地方式**: 批注 API **v1.7 Phase 2 早已存在** (`backend/api/annotations.py` 全 CRUD, 11 契约测试)——方案第三次事实修正 (原以为缺薄 API)。实际后端工作 = migration 118 (`ALTER ADD quote` 列) + service/router 透传 quote + create/delete 审计 (annotation.*)。
- **B+ 锚点 (DD-7)**: quote=高亮原文 (≤500 字) + range=原始 content 偏移; 渲染端四步解析 (快路径 → ±2000 窗内重锚 → 全文兜底 → stale), 永不静默错放。
- **已交付**: 正文 mark 高亮 (渲染器线性扫描注入, B+ 渲染丢失 bug 已修) / 选区批注 (quote 主锚, offset 仅 hint) / 侧栏三态 (定位/迁移/未定位) + 定位滚动 + 删除。
- **代码位置**: `frontend/src/components/reader/DeepReaderPage.tsx`; 后端 `annotations.py` / `annotation_service.py` / `annotations_repo.py`
- **注**: 正文的 markdown 渲染为子集 (标题/列表/加粗); 行内码按原文显示

### 5. (无缺口) 校对室

计划表曾标注 `/api/info-filter/rules` 缺失, 实现核对时确认该端点已随 v0.8 P1 批次落地 (`info_filter_api.py`, 6 端点), 因此校对室为全真实数据。info_filter 为 feature gate (默认开), gate 关闭时规则区降级为「接口不可用」空态。

## 排期建议

> 2026-09-16 更新: 三项全部并入收尾批方案 `docs/UI_REFACTOR_FOLLOWUP_PLAN_2026-09-16.md` (批次 C), 优先级 C1 (0 后端) > C2 (薄 API) > C3 (聚合端点)。

| 项 | 建议批次 |
|---|---|
| 编目室接真实数据 (复用 /api/knowledge/items, 0 后端) | 收尾批 C1 (0.5 天) |
| annotations 薄 API + B+ 锚点 (migration 118 加 quote 列, 已批) + reader 接线 | 收尾批 C2 (1–1.5 天) |
| hub-stats 聚合端点 + khub 切换 | 收尾批 C3 (0.5–1 天) |
