# Phase 7 — MCP Server 任务分解

> **spec**: [spec.md](./spec.md)
> **PRD**: [hotspot_v1.7_PRD.md §16](file:///Users/duke/Documents/hotspot/docs/hotspot_v1.7_PRD.md)
> **Group 划分**: A(migrations) → B(mcp_core) → C(cleanup) → D(frontend) → E(tests) → F(docs)
> **总周期**: ~16 小时 (2.5 工作日)

---

## Group A: DB 迁移

### Task A1: migration 037 — mcp_tool_registry 新表 ✅

**Files:**
- Create: `backend/repository/migrations/037_v1.7_mcp_tool_registry.sql`

- [x] **Step 1**: 创建迁移文件，含 mcp_tool_registry 表 + 2 个索引（category / enabled），SQL 见 spec §3.1
- [x] **Step 2**: 手动执行：`sqlite3 backend/hotspot.db < backend/repository/migrations/037_v1.7_mcp_tool_registry.sql`
- [x] **Step 3**: 验证表存在：`sqlite3 backend/hotspot.db ".schema mcp_tool_registry"`
- [x] **Step 4**: Commit: `feat(v1.7): A1 add 037 mcp_tool_registry table`

### Task A2: migration 038 — DROP 5 张 Phase 5 表 ✅

**Files:**
- Create: `backend/repository/migrations/038_v1.7_drop_phase5_tables.sql`
- Create: `backend/data/dropped_tables_snapshot_2026-07-25.sql`（删表前 7 天快照）

- [x] **Step 1**: 创建迁移文件，DROP knowledge_tasks / agent_heartbeats / agent_task_skills / skill_config / mcp_tool_invocations（kv_cache 保留），SQL 见 spec §3.3
- [x] **Step 2**: 删表前审计：`sqlite3 backend/hotspot.db "SELECT COUNT(*) FROM knowledge_tasks"` 确认无活跃任务
- [x] **Step 3**: 导出快照：`sqlite3 backend/hotspot.db ".dump knowledge_tasks agent_heartbeats agent_task_skills skill_config mcp_tool_invocations" > backend/data/dropped_tables_snapshot_2026-07-25.sql`
- [x] **Step 4**: 执行迁移：`sqlite3 backend/hotspot.db < backend/repository/migrations/038_v1.7_drop_phase5_tables.sql`
- [x] **Step 5**: 验证：`sqlite3 backend/hotspot.db ".tables" | grep -E "knowledge_tasks|agent_heart|skill_config|mcp_tool_inv"` 应为空
- [x] **Step 6**: Commit: `feat(v1.7): A2 drop 5 Phase 5 tables (Option A cleanup)` (合并入 8e7b939)

### Task A3: migration 039 — favorites.created_via 列 ✅

**Files:**
- Create: `backend/repository/migrations/039_v1.7_add_favorite_source.sql`

- [x] **Step 1**: 创建迁移文件，ALTER favorites ADD COLUMN created_via TEXT NOT NULL DEFAULT 'ui' CHECK (created_via IN ('ui', 'mcp', 'agent'))，SQL 见 spec §3.2
- [x] **Step 2**: 执行：`sqlite3 backend/hotspot.db < backend/repository/migrations/039_v1.7_add_favorite_source.sql`
- [x] **Step 3**: 验证：`sqlite3 backend/hotspot.db ".schema favorites"` 含 created_via
- [x] **Step 4**: 验证现有数据：`SELECT COUNT(*), created_via FROM favorites GROUP BY created_via` 全部 'ui'
- [x] **Step 5**: Commit: `feat(v1.7): A3 add favorites.created_via column (mcp/agent source tracking)` (合并入 8e7b939)

---

## Group B: MCP Server 核心

### Task B1: 依赖 + 类型定义 ✅

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/api/mcp_types.py`

- [x] **Step 1**: `requirements.txt` 追加 `fastapi-mcp>=0.4.0,<1.0`
- [x] **Step 2**: 验证安装：`.venv/bin/pip install fastapi-mcp` 不报错
- [x] **Step 3**: 在 `backend/api/mcp_types.py` 定义 13 个 tool 的 Pydantic input model
- [x] **Step 4**: Commit: `feat(v1.7): B1 add fastapi-mcp dep + MCP tool type definitions` (合并入 8e7b939)

### Task B2: mcp_config.py — FastApiMCP 集成 ✅

**Files:**
- Create: `backend/api/mcp_config.py`

- [x] **Step 1**: 实现 `build_mcp_server(app)` 函数，配置 FastApiMCP + include_operations 13 个
- [x] **Step 2**: 实现 `mcp_tool_registry_seed()` 函数，启动时把 13 个 tool 元数据写入 mcp_tool_registry 表（name, category, description, input_schema）
- [x] **Step 3**: 实现 `is_mcp_enabled()` 函数，读 settings kv 检查 feature.mcp_server
- [x] **Step 4**: 验证：`.venv/bin/python -c "from backend.api.mcp_config import build_mcp_server; print('OK')"`
- [x] **Step 5**: Commit: `feat(v1.7): B2 add mcp_config.py with FastApiMCP + tool registry seeding` (合并入 8e7b939)

### Task B3: mcp_stdio_main.py — stdio 入口 ✅

**Files:**
- Create: `backend/mcp_stdio_main.py`

- [x] **Step 1**: 实现 stdio transport 入口，调 `mcp.run(transport="stdio")`
- [x] **Step 2**: 实现启动日志：banner + feature flag 检查 + 监听地址
- [x] **Step 3**: 验证：`python -m backend.mcp_stdio_main` 启动后等待 stdin
- [x] **Step 4**: Commit: `feat(v1.7): B3 add MCP stdio entry point` (合并入 8e7b939; 56afa9c 修正 setup_logging→setup)

### Task B4: main.py — lifespan 集成 + 启动 seeding ✅

**Files:**
- Modify: `backend/main.py`

- [x] **Step 1**: 在 FastAPI lifespan 中注册 MCP server（lifespan startup 调 mcp_tool_registry_seed + 挂载 SSE endpoint）
- [x] **Step 2**: 在 main.py 调 `build_mcp_server(app)` 并 `mcp.mount_sse_endpoint(path="/mcp/sse")`
- [x] **Step 3**: 启动后日志打印 `MCP server: 13 tools exposed at /mcp/sse (transport: stdio | sse)`
- [x] **Step 4**: Commit: `feat(v1.7): B4 register MCP server in FastAPI lifespan + SSE mount` (合并入 8e7b939)

### Task B5: /api/mcp.py — 调试端点 ✅

**Files:**
- Create: `backend/api/mcp.py`

- [x] **Step 1**: 实现 2 个端点（GET /api/mcp/status + GET /api/mcp/tools），状态包含 enabled/transport/tools_count
- [x] **Step 2**: tools 端点从 mcp_tool_registry 表读 13 个 tool 元数据
- [x] **Step 3**: 实现 `GET /api/settings/mcp/config` + `PUT /api/settings/mcp/enabled`（toggle feature.mcp_server）
- [x] **Step 4**: include_router 到 main.py
- [x] **Step 5**: Commit: `feat(v1.7): B5 add /api/mcp and /api/settings/mcp endpoints` (合并入 8e7b939)

---

## Group C: Phase 5 清理（Option A 关键）

### Task C1: 删除 agent/ 目录 + 4 service 文件 ✅

**Files:**
- Delete: `agent/` 整目录
- Delete: `backend/services/agent_task_service.py`
- Delete: `backend/services/agent_protocol.py`
- Delete: `backend/services/kv_cache_service.py`
- Delete: `backend/services/skill_config_service.py`（如存在）

- [x] **Step 1**: 确认 `agent/` 目录无活跃进程：`lsof | grep -i hotspot-agent` 应为空
- [x] **Step 2**: `rm -rf agent/`
- [x] **Step 3**: 删除 4 个 service 文件
- [x] **Step 4**: 全局搜索残留引用：`grep -rn "from backend.services.agent_task_service\|from backend.services.agent_protocol\|from backend.services.kv_cache_service\|from backend.services.skill_config_service" backend/ frontend/src/`
- [x] **Step 5**: 修复所有残留 import（如有）
- [x] **Step 6**: 验证编译：`.venv/bin/python -m py_compile backend/main.py`
- [x] **Step 7**: Commit: `refactor(v1.7): C1 delete agent/ directory and 4 Phase 5 service files (Option A)` (合并入 8e7b939)

### Task C2: 降级 /api/agent.py 端点 ✅

**Files:**
- Modify: `backend/api/agent.py`（保留 4 个 deprecated，重写或缩减）
- Modify: `backend/main.py`（include_router 调整）

- [x] **Step 1**: 重写 `backend/api/agent.py`，仅保留 4 个 deprecated GET 端点（tasks / tasks/{id}/complete / tasks/{id}/status / knowledge），加 `@deprecated` 装饰器
- [x] **Step 2**: 移除 6 个端点：/start /stop /restart /status /heartbeat /agent/knowledge POST
- [x] **Step 3**: main.py include_router 调整（如有变化）
- [x] **Step 4**: Commit: `refactor(v1.7): C2 deprecate /api/agent/* to 4 GET endpoints (Option A)` (合并入 8e7b939)

### Task C3: 删除 5 个 Phase 5 调度器 job ✅

**Files:**
- Modify: `backend/scheduler/jobs.py`
- Modify: `backend/scheduler/scheduler.py`

- [x] **Step 1**: 删除 `agent_task_consumer_job` / `agent_heartbeat_check_job` / `kv_cache_cleanup_job` / `auto_extract_llm_job` / `review_scheduler_llm_job` 5 个函数
- [x] **Step 2**: 从 `jobs.__all__` 移除 5 个名字
- [x] **Step 3**: 从 `scheduler.py` 移除 5 个 scheduler.add_job() 调用
- [x] **Step 4**: 验证：`.venv/bin/python -c "from backend.scheduler.jobs import *; print(__all__)"` 不含被删 job
- [x] **Step 5**: Commit: `refactor(v1.7): C3 remove 5 Phase 5 scheduler jobs (Option A)` (合并入 8e7b939)

### Task C4: 清空 tasks/{pending,processing}/ 目录 ✅

**Files:**
- Delete: `knowledge/learning/tasks/pending/*.md`
- Delete: `knowledge/learning/tasks/processing/*.md`

- [x] **Step 1**: 审计 pending/ 目录内容：`ls -la knowledge/learning/tasks/pending/`
- [x] **Step 2**: 确认无活跃任务（task-XXX.md 应都是 hot_take_collect 残留）
- [x] **Step 3**: `rm -f knowledge/learning/tasks/pending/*.md`
- [x] **Step 4**: `rm -f knowledge/learning/tasks/processing/*.md`
- [x] **Step 5**: 保留 done/ 和 failed/ 历史归档
- [x] **Step 6**: 提交后 git rm tracked files（如有）
- [x] **Step 7**: Commit: `chore(v1.7): C4 clear tasks/{pending,processing}/ for Option A` (合并入 8e7b939)

### Task C5: feature_flag — 移除 agent flag + 新增 mcp_server flag 🟡

**Files:**
- Modify: `backend/services/feature_flag_service.py`
- Modify: `backend/config.py`（feature_* 字段）

- [x] **Step 1**: config.py 移除 `feature_agent: bool = True` 字段
- [x] **Step 2**: config.py 新增 `feature_mcp_server: bool = True`（Option A 默认 on）
- [ ] **Step 3**: feature_flag_service.py 移除 `agent` flag 引用 + docstring 修正 (待办: 见 56afa9c 同批)
- [x] **Step 4**: 全局搜索残留引用：`grep -rn "is_enabled.\"agent\"\|feature.agent" backend/ frontend/src/`
- [x] **Step 5**: 修复残留引用（如有）
- [x] **Step 6**: 验证：`.venv/bin/python -c "from backend.services.feature_flag_service import is_enabled; print(is_enabled('mcp_server'))"`
- [ ] **Step 7**: Commit: `feat(v1.7): C5 replace feature.agent with feature.mcp_server (default on)` (待办)

### Task C6: 全量回归 — Phase 1-6 测试无影响 ⏳

**Files:**
- Run: `.venv/bin/python -m pytest backend/tests/test_v1_7_e2e.py backend/tests/test_migrations_v1_7.py backend/tests/test_sync_bundle_v1_7.py backend/tests/test_feature_flags.py -v`

- [ ] **Step 1**: 运行 Phase 1-6 全部回归测试
- [ ] **Step 2**: 全部 PASS，无任何 skip
- [ ] **Step 3**: 若有失败，创建修复子任务
- [ ] **Step 4**: 记录：`Phase 1-6 regression: X/X PASS`

---

## Group D: 前端

### Task D1: MCPSettingsCard 组件 ✅

**Files:**
- Create: `frontend/src/components/settings/MCPSettingsCard.tsx`

- [x] **Step 1**: 实现组件（mockup 见 spec §8.3）：enable toggle + transport radio + stdio 配置代码块 + 复制按钮 + 13 tool 列表
- [x] **Step 2**: 调 `GET /api/settings/mcp/config` 拉配置，调 `PUT /api/settings/mcp/enabled` 切换
- [x] **Step 3**: 复制按钮用 `navigator.clipboard.writeText()`，成功后 toast 提示
- [x] **Step 4**: 13 tool 列表分 5 读 + 8 写两段，checkbox 来自 `GET /api/mcp/tools`
- [x] **Step 5**: Commit: `feat(v1.7): D1 add MCPSettingsCard component` (合并入 8e7b939)

### Task D2: SettingsPage 内嵌 MCPSettingsCard ✅

**Files:**
- Modify: `frontend/src/components/SettingsPage.tsx`
- Modify: `frontend/src/components/settings/index.tsx`（如存在）

- [x] **Step 1**: 在 SettingsPage 追加一栏「MCP Server」
- [x] **Step 2**: 导入并渲染 `<MCPSettingsCard />`（实际在 `settings/index.tsx` 的 `SettingsPanel` 中渲染，与 PRD 等价）
- [x] **Step 3]: 验证：访问 /settings 看到 MCP 卡片
- [x] **Step 4]: Commit: `feat(v1.7): D2 embed MCPSettingsCard in SettingsPage` (合并入 8e7b939)

### Task D3: 路由 + 删除 /agent 残留 ✅

**Files:**
- Modify: `frontend/src/App.tsx`

- [x] **Step 1**: 删除 `/agent` 路由（如有）— grep 确认无残留
- [x] **Step 2]: 添加 `/settings/mcp` 路由（如有需要，否则在 SettingsPage 内部 anchor）
- [x] **Step 3]: 删除 `import` AgentPage / AgentStatusBadge / 5 tab 组件
- [x] **Step 4]: 全局搜索残留：`grep -rn "AgentPage\|AgentStatusBadge" frontend/src/`
- [x] **Step 5]: 修复残留
- [x] **Step 6]: 验证：`cd frontend && npm run build` 0 错误
- [x] **Step 7]: Commit: `refactor(v1.7): D3 remove /agent route + add /settings/mcp` (合并入 8e7b939)

---

## Group E: 测试

### Task E1: 后端单测 — MCP server 基础 ✅

**Files:**
- Create: `backend/tests/test_mcp_server.py`

- [x] **Step 1**: 测试 fastapi-mcp 启动 / 关闭 + tools/list 返回 13 个 tool
- [x] **Step 2]: 测试 mcp_tool_registry seeding 幂等性（重启不重复插入）
- [x] **Step 3]: 测试 feature.mcp_server toggle → /api/mcp/status 反映
- [x] **Step 4]: 写 6 个测试
- [x] **Step 5]: 运行：`.venv/bin/python -m pytest backend/tests/test_mcp_server.py -v`
- [x] **Step 6]: Commit: `test(v1.7): E1 add test_mcp_server.py (6 tests)` (合并入 8e7b939)

### Task E2: 后端集成测试 — MCP 读 tool ✅

**Files:**
- Create: `backend/tests/test_mcp_read_tools.py`

- [x] **Step 1]: 5 个读 tool 路由到正确 FastAPI 端点（search_hotspots / get_hotspot / list_favorites / search_knowledge / get_personal_profile）
- [x] **Step 2]: 验证输入参数校验（Pydantic schema）
- [x] **Step 3]: 验证响应 JSON 结构
- [x] **Step 4]: 写 10 个测试
- [x] **Step 5]: 运行：`.venv/bin/python -m pytest backend/tests/test_mcp_read_tools.py -v`
- [x] **Step 6]: Commit: `test(v1.7): E2 add test_mcp_read_tools.py (10 tests)` (合并入 8e7b939)

### Task E3: 后端集成测试 — MCP 写 tool ✅

**Files:**
- Create: `backend/tests/test_mcp_write_tools.py`

- [x] **Step 1]: 8 个写 tool 同步直返（add_favorite / remove_favorite / add_annotation / update_knowledge_item / trigger_extract_tags / trigger_cubox_sync / create_alert_rule / mark_digest_read）
- [x] **Step 2]: 特别验证 add_favorite 写 created_via='mcp'
- [x] **Step 3]: 验证 trigger_extract_tags 不调 LLM（mock 检查）
- [x] **Step 4]: 写 12 个测试
- [x] **Step 5]: 运行：`.venv/bin/python -m pytest backend/tests/test_mcp_write_tools.py -v`
- [x] **Step 6]: Commit: `test(v1.7): E3 add test_mcp_write_tools.py (12 tests)` (合并入 8e7b939)

### Task E4: 后端集成测试 — MCP transport ✅

**Files:**
- Create: `backend/tests/test_mcp_stdio.py`
- Create: `backend/tests/test_mcp_sse.py`

- [x] **Step 1]: test_mcp_stdio.py: subprocess 启动 stdio 入口，模拟外部 agent 通过 stdin/stdout 调 tool
- [x] **Step 2]: test_mcp_sse.py: HTTP client 连 /mcp/sse，调 tools/list + search_hotspots
- [x] **Step 3]: 写 4 + 4 = 8 个测试
- [x] **Step 4]: 运行：`.venv/bin/python -m pytest backend/tests/test_mcp_stdio.py backend/tests/test_mcp_sse.py -v`
- [x] **Step 5]: Commit: `test(v1.7): E4 add test_mcp_stdio + test_mcp_sse (8 tests)` (c031e69)

### Task E5: 后端测试 — 删表迁移 + favorites.created_via 🟡

**Files:**
- Create: `backend/tests/test_phase5_table_cleanup.py` ✅
- Create: `backend/tests/test_favorite_created_via.py` ⏳ (待办)

- [x] **Step 1]: test_phase5_table_cleanup.py: 验证 migration 038 可重放，5 张表 DROP 后现有数据无影响
- [ ] **Step 2]: test_favorite_created_via.py: 验证 add_favorite MCP 写 created_via='mcp'，UI 写 'ui'，默认值为 'ui' (待办)
- [x] **Step 3]: 写 6 + 4 = 10 个测试 (test_phase5_table_cleanup.py 6/6)
- [ ] **Step 4]: 运行：`.venv/bin/python -m pytest backend/tests/test_phase5_table_cleanup.py backend/tests/test_favorite_created_via.py -v`
- [ ] **Step 5]: Commit: `test(v1.7): E5 add table cleanup + favorite created_via tests (10 tests)`

### Task E6: E2E — 模拟 Cursor 调 MCP 全链路 ✅

**Files:**
- Create: `backend/tests/test_phase7_e2e.py`

- [x] **Step 1]: test_external_agent_writes_through_mcp: 启动 hotspot + 模拟 Cursor 通过 stdio 调 add_favorite，验证 SQLite favorites 表 + knowledge/items/{id}.md 都更新
- [x] **Step 2]: test_mcp_sse_transport: 启动 hotspot，httpx-sse 连 /mcp/sse，tools/list 验证 13 tool + search_hotspots 响应
- [x] **Step 3]: 写 2 个 e2e 测试
- [x] **Step 4]: 运行：`.venv/bin/python -m pytest backend/tests/test_phase7_e2e.py -v`
- [x] **Step 5]: Commit: `test(v1.7): E6 add test_phase7_e2e.py (MCP write + SSE transports)` (合并入 8e7b939)

### Task E7: 前端组件测试 — MCPSettingsCard ✅

**Files:**
- Create: `frontend/src/components/settings/MCPSettingsCard.test.tsx`

- [x] **Step 1]: 测试：复制按钮 / 13 个 tool 列表渲染 / enabled toggle 调 API
- [x] **Step 2]: mock fetch `/api/settings/mcp/config` + `/api/mcp/tools` + `/api/settings/mcp/enabled`
- [x] **Step 3]: 写 6-8 个测试
- [x] **Step 4]: 运行：`cd frontend && npx vitest run src/components/settings/MCPSettingsCard.test.tsx`
- [x] **Step 5]: Commit: `test(v1.7): E7 add MCPSettingsCard.test.tsx (6+ tests)` (合并入 8e7b939)

---

## Group F: 文档

### Task F1: docs/mcp_integration.md — AI Agent 配置指南 ✅

**Files:**
- Create: `docs/mcp_integration.md`

- [x] **Step 1]: 写用户配置指南：Cursor / Claude Desktop / Trae / Workbuddy 4 个 AI Agent 的 settings.json 示例
- [x] **Step 2]: 13 个 tool 的详细使用场景 + 输入输出示例
- [x] **Step 3]: 性能预期 + 限制说明（127.0.0.1 默认 / 0.0.0.0 需手动）
- [x] **Step 4]: Commit: `docs(v1.7): F1 add mcp_integration.md` (合并入 8e7b939)

### Task F2: docs/mcp_vs_phase5.md — Option A 选型说明 ✅

**Files:**
- Create: `docs/mcp_vs_phase5.md`

- [x] **Step 1]: 写 Option A vs Phase 5 内部 hotspot-agent 的对比
- [x] **Step 2]: 解释为什么移除 knowledge_tasks / heartbeat / agent process
- [x] **Step 3]: 删表 / 删 API / 删 job 详细清单
- [x] **Step 4]: Commit: `docs(v1.7): F2 add mcp_vs_phase5.md` (合并入 8e7b939)

### Task F3: docs/phase7_changelog.md — Phase 7 变更日志 ✅

**Files:**
- Create: `docs/phase7_changelog.md`

- [x] **Step 1]: 写删表清单（5 张）+ 删 API 清单（6 个端点）+ 删 job 清单（5 个）+ 删文件清单（agent/ 目录 + 4 service）
- [x] **Step 2]: 写新增清单（1 表 + 1 改 + 13 tool + 1 组件 + 4 文档）
- [x] **Step 3]: 写迁移路径（旧用户如何升级）
- [x] **Step 4]: Commit: `docs(v1.7): F3 add phase7_changelog.md` (50581fb)

### Task F4: docs/mcp_tools_schema.json — 13 tool JSON Schema ✅

**Files:**
- Create: `docs/mcp_tools_schema.json`

- [x] **Step 1]: 写 13 个 tool 的 input_schema（JSON Schema 格式）
- [x] **Step 2]: 写 output_schema 概要
- [x] **Step 3]: 写权限说明（哪些写 / 哪些读 / 哪些需要 feature flag）
- [x] **Step 4]: Commit: `docs(v1.7): F4 add mcp_tools_schema.json` (8b4b6c6)

---

## 总计

- **任务数**: 28 (A:3 + B:5 + C:6 + D:3 + E:7 + F:4)
- **预期 commit 数**: ~28
- **预期新增迁移**: 3 (037, 038, 039)
- **预期新增 API**: 3 (mcp/status, mcp/tools, settings/mcp/config)
- **预期新增前端组件**: 1 (MCPSettingsCard)
- **预期新增测试**: ~52 后端 + 7 前端 = ~59
- **预期删除**: 5 张表 + 6 个端点 + 5 个 job + 1 个目录 + 4 个 service 文件
- **预期新增文档**: 4

## Task Dependencies

```
Group A (迁移)
  ↓
Group B (MCP core) — 依赖 A
  ↓
Group C (清理) — 可与 B 并行
  ↓
Group D (前端) — 依赖 B
  ↓
Group E (测试) — 依赖 B + C
  ↓
Group F (文档) — 最后写, 可与 E 并行
```

**可并行执行**:
- A1 / A2 / A3 (3 个迁移可同时执行)
- B1 / C1 / C3 (依赖 + 文件删除可同时)
- E1 / E2 / E3 / E4 / E5 / E7 (测试文件独立, 可并行写)

## Commit 信息规范

按项目已有 convention:
- `feat(v1.7): [Group][Task] ...` — 新功能
- `refactor(v1.7): [Group][Task] ...` — 重构
- `test(v1.7): [Group][Task] ...` — 测试
- `docs(v1.7): [Group][Task] ...` — 文档
- `chore(v1.7): [Group][Task] ...` — 杂项

每 commit 含明确范围，不夹带与该任务无关的改动。

## 关键风险点（需重点 attention）

1. **Task A2 删表**: 必须先审计 knowledge_tasks 无活跃任务，否则导致数据丢失
2. **Task B2 fastapi-mcp 集成**: 与现有中间件（CORS / 鉴权）可能冲突，需先在 staging 验证
3. **Task C1 全局搜索残留**: 删除 4 个 service 文件后，所有 import 都要修复
4. **Task C3 scheduler job 删除**: 确保无其他模块依赖这 5 个 job 函数
5. **Task E6 E2E**: 启动 stdio 子进程需小心 timeout，AI Agent mock 应使用真实 MCP 协议格式

## 总验证（项目级）

- [ ] 后端全量测试 PASS（含 Phase 1-6 + Phase 7）
- [ ] 前端 vitest PASS
- [ ] 前端 `npm run build` 0 错误
- [ ] 启动 hotspot 后访问 `/api/mcp/status` 返回 13 tool
- [ ] 启动 stdio 后能列出 13 tool
- [ ] git log 显示 Phase 7 全部 commit
- [ ] 文档完整（4 篇 mcp_*.md / phase7_changelog.md / mcp_tools_schema.json）
- [ ] 旧 Phase 5 端点访问 404（deleted）/ 200（deprecated GET）
