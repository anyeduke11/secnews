# Phase 8 — 复利基础设施 + 资讯收藏聚合 任务分解

> **spec**: `.trae/specs/phase8-v2-compounding/spec.md`
> **Group 划分**: A(migration) → B(simhash) → C(mcp) → D(aggregator-be) → E(aggregator-fe) → F(test)

---

## Group A: DB Schema（migration 043）

### Task A1: 迁移文件 043_v2.0_fingerprints_scores.sql

**Files:**
- Create: `backend/repository/migrations/043_v2.0_fingerprints_scores.sql`

注: db.py 的 _apply_migrations 自动扫描 migrations/*.sql 按字典序加载，无需修改 db.py。

- [x] **Step 1**: 创建迁移文件，含 4 张表（content_fingerprints / ai_scores / item_entities / knowledge_links）+ 6 个索引，SQL 内容见 spec §3.1
- [x] **Step 2**: 手动执行迁移验证：`.venv/bin/python -c "from backend.repository.db import init_db; init_db()"`
- [x] **Step 3**: sqlite3 验证 4 张表存在：`sqlite3 backend/hotspot.db ".tables" | grep -E "content_fingerprints|ai_scores|item_entities|knowledge_links"`
- [x] **Step 4**: 提交: `feat(db): A1 migration 043 — add 4 tables for v2.0 compounding (fingerprints/scores/entities/links)`

### Task A2: knowledge_repo.list_items() 扩展

**Files:**
- Modify: `backend/repository/knowledge_repo.py`

- [x] **Step 1**: 扩展 `list_items()` 方法，新增 `sources`/`keyword`/`exclude_urls` 参数
- [x] **Step 2**: 实现 SQL 筛选逻辑（sources IN (...) / keyword LIKE / url NOT IN (...))
- [x] **Step 3**: 提交: `feat(repo): A2 extend knowledge_repo.list_items() with sources/keyword/exclude_urls filters`

---

## Group B: simhash 去重

### Task B1: simhash 实现

**Files:**
- Create: `backend/services/simhash.py`
- Create: `backend/tests/test_simhash.py`

- [x] **Step 1**: 实现 64-bit simhash 计算函数 `simhash(text: str) -> int`
- [x] **Step 2**: 实现 Hamming distance 函数 `hamming_distance(a: int, b: int) -> int`
- [x] **Step 3**: 实现 URL canonicalize 函数 `canonicalize_url(url: str) -> str`（去除 tracking params、hash、统一 https/http）
- [x] **Step 4**: 实现 title 规范化函数 `normalize_title(title: str) -> str`（小写、去除标点、trim）
- [x] **Step 5**: 写 5 个单测（碰撞测试、Hamming 距离、URL canonicalize、空输入、边界）
- [x] **Step 6**: 运行：`.venv/bin/python -m pytest backend/tests/test_simhash.py -v`
- [x] **Step 7**: 提交: `feat(services): B1 add simhash 64-bit + Hamming distance + URL canonicalize`

### Task B2: 去重集成

**Files:**
- Modify: `backend/services/collection_service.py`
- Create: `backend/tests/test_fingerprint.py`

- [x] **Step 1**: 在 `collect()` 完成后插入去重流程：计算 simhash → 查询 content_fingerprints → 重复则跳过
- [x] **Step 2**: 不重复时写入 content_fingerprints 表，记录 simhash / url_canonical / title_norm
- [x] **Step 3**: 重复内容记录 `duplicate_count` 统计（hotspots 表或日志）
- [x] **Step 4**: 写 5 个单测（指纹写入、去重检测、重复跳过、索引验证、边界）
- [x] **Step 5**: 运行：`.venv/bin/python -m pytest backend/tests/test_fingerprint.py -v`
- [x] **Step 6**: 提交: `feat(services): B2 integrate simhash dedup into collection_service`

---

## Group C: MCP Tool

### Task C1: 4 个新 MCP tool

**Files:**
- Create: `backend/api/mcp_phase8.py`
- Modify: `backend/api/__init__.py`（register_routers 添加 mcp_phase8）
- Create: `backend/tests/test_mcp_phase8.py`

- [x] **Step 1**: 创建 `mcp_phase8.py`，定义 4 个 ToolDef 的 input_schema（见 spec §4.1）
- [x] **Step 2**: 实现 `score_item` handler：写入 ai_scores 表，返回 `{status: "ok", score_id: N}`
- [x] **Step 3**: 实现 `enrich_concept` handler：写入 `concepts/{name}.md`，返回 `{status: "ok", file: "..."}`
- [x] **Step 4**: 实现 `link_items` handler：写入 knowledge_links 表，更新 knowledge_items 计数，返回 `{status: "ok", link_id: N}`
- [x] **Step 5**: 实现 `trigger_codegarden_drift` handler：评估 project tech_stack，返回 `{status: "ok", drift_score: 0.8}`
- [x] **Step 6**: 在 `api/__init__.py` 的 `register_routers()` 中注册 `mcp_phase8` 路由
- [x] **Step 7**: 写 8 个单测（4 tool × 2 用例：正常 + 异常）
- [x] **Step 8**: 运行：`.venv/bin/python -m pytest backend/tests/test_mcp_phase8.py -v`
- [x] **Step 9**: 提交: `feat(api): C1 add 4 new MCP tools (score_item/enrich_concept/link_items/trigger_codegarden_drift)`

---

## Group D: 资讯收藏聚合后端

### Task D1: imported_aggregator service

**Files:**
- Create: `backend/services/imported_aggregator.py`
- Create: `backend/tests/test_imported_aggregator.py`

- [x] **Step 1**: 实现 `ImportedAggregator` 类，5 源数据读取：
  - `_get_favorites()`: favorites_repo.list()
  - `_get_secnews()`: knowledge_repo.list_items() with source filter
  - `_get_cubox()`: 读取 cubox 缓存文件
  - `_get_bookmarks()`: 读取 bookmark JSON 文件
  - `_get_secnews_archive()`: 读取 secnews_archive 标记
- [x] **Step 2**: 实现合并去重逻辑（URL 去重，favorites 优先保留）
- [x] **Step 3**: 实现排序（ingested_at DESC）+ 分页
- [x] **Step 4**: 实现筛选参数（type / keyword / since / until）
- [x] **Step 5**: 写 8 个单测（5 源合并、去重、分页、keyword 筛选、type 筛选、时间范围、空结果、边界）
- [x] **Step 6**: 运行：`.venv/bin/python -m pytest backend/tests/test_imported_aggregator.py -v`
- [x] **Step 7**: 提交: `feat(services): D1 add ImportedAggregator for 5-source knowledge imported view`

### Task D2: 资讯收藏聚合 API

**Files:**
- Create: `backend/api/knowledge_imported.py`
- Modify: `backend/api/__init__.py`（register_routers 添加 knowledge_imported）
- Create: `backend/tests/test_knowledge_imported_api.py`

- [x] **Step 1**: 创建 `knowledge_imported.py`，实现 `GET /api/knowledge/imported`
- [x] **Step 2**: 参数解析：type / keyword / since / until / page / page_size
- [x] **Step 3**: 调用 `ImportedAggregator.get_items()` 获取数据
- [x] **Step 4**: 返回统一格式的 JSON 响应（items + total + page + page_size）
- [x] **Step 5**: 错误处理：参数校验、空结果、异常兜底
- [x] **Step 6**: 在 `api/__init__.py` 的 `register_routers()` 中注册 `knowledge_imported` 路由
- [x] **Step 7**: 写 7 个单测（API 参数、分页、type 筛选、keyword 搜索、时间范围、错误处理、空结果）
- [x] **Step 8**: 运行：`.venv/bin/python -m pytest backend/tests/test_knowledge_imported_api.py -v`
- [x] **Step 9**: 提交: `feat(api): D2 add GET /api/knowledge/imported endpoint`

---

## Group E: 资讯收藏聚合前端

### Task E1: useImported hook + API

**Files:**
- Create: `frontend/src/hooks/useImported.ts`

- [x] **Step 1**: 实现 `useImported` hook，封装 `GET /api/knowledge/imported` 调用
- [x] **Step 2**: 参数：type / keyword / since / until / page / page_size
- [x] **Step 3**: 返回：items / total / page / pageSize / loading / error
- [x] **Step 4**: 提交: `feat(hooks): E1 add useImported hook for knowledge imported API`

### Task E2: KnowledgeFavoritesView 组件

**Files:**
- Create: `frontend/src/components/knowledge/KnowledgeFavoritesView.tsx`
- Create: `frontend/src/components/knowledge/KnowledgeFavoritesView.test.tsx`

- [x] **Step 1**: 实现组件渲染 5 源列表（卡片式布局，显示 source_type 标签）
- [x] **Step 2**: 实现 5 类型筛选（tags/下拉菜单，单选/多选）
- [x] **Step 3**: 实现名称搜索（input + debounce 300ms）
- [x] **Step 4**: 实现时间范围选择（起止日期 picker）
- [x] **Step 5**: 实现分页（上一页/下一页/页码 + page_size 选择）
- [x] **Step 6**: 写 5 个组件测试（渲染、筛选、搜索、分页、空状态）
- [x] **Step 7**: 运行：`cd frontend && npx vitest run src/components/knowledge/KnowledgeFavoritesView.test.tsx`
- [x] **Step 8**: 提交: `feat(ui): E2 add KnowledgeFavoritesView component with filters/search/pagination`

### Task E3: 路由 + 导航集成

**Files:**
- Modify: `frontend/src/App.tsx`

- [x] **Step 1**: 配置路由 `/knowledge/imported` → `KnowledgeFavoritesView`
- [x] **Step 2**: 在导航栏添加 5th action card（"资讯收藏"入口）
- [x] **Step 3**: 提交: `feat(ui): E3 add /knowledge/imported route + 5th action card`

---

## Group F: 测试与验证

### Task F1: 全量测试

- [x] **Step 1**: 运行后端全量 Phase 8 测试：`.venv/bin/python -m pytest backend/tests/test_simhash.py backend/tests/test_fingerprint.py backend/tests/test_mcp_phase8.py backend/tests/test_imported_aggregator.py backend/tests/test_knowledge_imported_api.py -v`
- [x] **Step 2**: 运行前端全量组件测试：`cd frontend && npx vitest run src/components/knowledge/KnowledgeFavoritesView.test.tsx`
- [x] **Step 3**: 编译检查：`.venv/bin/python -m py_compile backend/services/simhash.py && .venv/bin/python -m py_compile backend/api/mcp_phase8.py && .venv/bin/python -m py_compile backend/services/imported_aggregator.py`
- [x] **Step 4**: 类型检查：`cd frontend && npx tsc --noEmit`
- [x] **Step 5**: 提交: `test(phase8): F1 all Phase 8 tests pass — simhash/mcp/fingerprint/aggregator/api`

### Task F2: 资讯收藏聚合 e2e 验证

- [x] **Step 1**: 启动 dev 环境（后端 + 前端）
- [x] **Step 2**: 验证 5th action card 可见且可点击
- [x] **Step 3**: 验证 5 类型筛选（favorites / cubox / bookmark / secnews_archive / secnews）
- [x] **Step 4**: 验证名称搜索（输入 keyword，列表过滤）
- [x] **Step 5**: 验证时间范围筛选（起止日期，列表过滤）
- [x] **Step 6**: 验证分页（下一页/上一页，页码正确）
- [x] **Step 7**: 验证空状态（无数据时显示提示）
- [x] **Step 8**: 验证性能（P95 < 300ms）

### Task F3: 文档更新

**Files:**
- Create: `docs/phase8_changelog.md`

- [x] **Step 1**: 创建 `docs/phase8_changelog.md`，记录 Phase 8 新增功能
- [x] **Step 2**: 提交: `docs(phase8): F3 add phase8 changelog`