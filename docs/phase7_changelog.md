# Phase 7 变更日志 (v1.7.6 Option A)

> **日期**: 2026-07-25
> **范围**: MCP Server 集成 + Phase 5 内部 hotspot-agent 清理
> **spec**: [phase7-mcp-server/spec.md](../.trae/specs/phase7-mcp-server/spec.md)
> **兼容性**: 破坏性变更（详见迁移路径）

## 1. 新增清单

### 1.1 数据库
- `mcp_tool_registry` 表（migration 037，13 tool 元数据）
- `favorites.created_via` 列（migration 039，enum: ui/mcp/agent）

### 1.2 API 端点
- `GET /api/mcp/status` — MCP server 状态
- `GET /api/mcp/tools` — 13 tool 元数据列表
- `GET /api/settings/mcp/config` — stdio/SSE 配置（前端复制用）
- `PUT /api/settings/mcp/enabled` — 切换 feature.mcp_server
- `GET /api/profile` — get_personal_profile 适配
- `POST /api/cubox/sync` — trigger_cubox_sync 适配
- `POST /api/extract/auto` — trigger_extract_tags 适配
- `POST /api/favorites/by-hotspot` — add_favorite MCP 友好入口

### 1.3 MCP Tools（13 个，5 读 + 8 写）
- 读: search_hotspots, get_hotspot, list_favorites, search_knowledge, get_personal_profile
- 写: add_favorite, remove_favorite, add_annotation, update_knowledge_item, trigger_extract_tags, trigger_cubox_sync, create_alert_rule, mark_digest_read

### 1.4 后端
- `backend/api/mcp_types.py` — 13 tool 的 Pydantic input schema
- `backend/api/mcp_config.py` — FastApiMCP 集成 + tool seeding
- `backend/api/mcp.py` — 调试/设置端点
- `backend/api/mcp_adapters.py` — MCP 适配端点
- `backend/mcp_stdio_main.py` — stdio transport 入口
- `requirements.txt` — 追加 `fastapi-mcp>=0.4.0,<1.0`
- `config.py` — 新增 `feature_mcp_server: bool = True`

### 1.5 前端
- `frontend/src/components/settings/MCPSettingsCard.tsx` — 设置卡片
- `frontend/src/components/settings/MCPSettingsCard.test.tsx` — 组件测试
- `frontend/src/components/settings/index.tsx` — 集成 MCP 卡片到设置面板

### 1.6 文档
- `docs/mcp_integration.md` — AI Agent 配置指南
- `docs/mcp_vs_phase5.md` — Option A 选型说明
- `docs/mcp_tools_schema.json` — 13 tool JSON Schema
- `docs/phase7_changelog.md` — 本文件

## 2. 删除清单

### 2.1 数据库（5 张表，migration 038）
- `knowledge_tasks` — 异步任务队列
- `agent_heartbeats` — 内部 agent 心跳
- `agent_task_skills` — agent 技能关联
- `skill_config` — 技能配置
- `mcp_tool_invocations` — tool 调用日志
- 备注: `kv_cache` 表保留（不在删除范围）

### 2.2 API 端点（6 个）
- `POST /api/agent/tasks` — 任务入队
- `POST /api/agent/tasks/{id}/complete` — 任务完成
- `POST /api/agent/knowledge` — 知识提交
- `POST /api/agent/start` — 启动 agent
- `POST /api/agent/stop` — 停止 agent
- `POST /api/agent/restart` — 重启 agent
- `GET /api/agent/status` — agent 状态
- `GET /api/agent/heartbeat` — agent 心跳

保留为 deprecated（仅 GET，返回 410 Gone 或空列表）：
- `GET /api/agent/tasks`
- `GET /api/agent/tasks/{id}`
- `GET /api/agent/tasks/{id}/status`
- `GET /api/agent/knowledge`

### 2.3 调度器（5 个 job）
- `agent_task_consumer_job` — 消费任务队列
- `agent_heartbeat_check_job` — 心跳检查
- `kv_cache_cleanup_job` — KV 缓存清理（NoOp 占位）
- `auto_extract_llm_job` — LLM 提取（本地规则替代）
- `review_scheduler_llm_job` — LLM 复习（UI 评分替代）

### 2.4 文件 / 目录
- `agent/` 整目录（cli.py / client.py / executor.py / poller.py / skills/）
- `backend/services/agent_task_service.py`
- `backend/services/agent_protocol.py`
- `backend/services/kv_cache_service.py`
- `backend/services/skill_config_service.py`

### 2.5 前端
- `/agent` 路由
- `<AgentPage />` + 5 个 tab 组件
- `<AgentStatusBadge />`

### 2.6 Feature Flag
- 移除 `feature_agent: bool = True` (config.py)
- 新增 `feature_mcp_server: bool = True`（替代）

## 3. 迁移路径（旧用户升级指南）

### 3.1 数据库迁移
- 启动前自动执行 migration 037/038/039（init_db 流程）
- 删表前快照: `backend/data/dropped_tables_snapshot_2026-07-25.sql`（7 天保留）

### 3.2 API 兼容
- 旧 `/api/agent/*` 写端点（POST start/stop/restart）直接 404
- 4 个 GET 端点降级为 deprecated（返回 410 Gone 或空列表 + 警告日志）
- 内部系统如依赖这些端点，必须切换到 MCP tool

### 3.3 Feature Flag
- `feature_agent` 字段从 config 移除
- 旧值（如 `True`）需手动迁移为 `feature_mcp_server`
- 默认 `feature.mcp_server=True`（Option A 默认开）

### 3.4 MCP 配置（AI Agent 侧）
- Cursor / Claude Desktop / Trae / Workbuddy: 配置 `mcpServers.hotspot`
- stdio: `python -m backend.mcp_stdio_main`
- SSE: `http://127.0.0.1:8000/mcp/sse`
- 详见 [mcp_integration.md](./mcp_integration.md)

## 4. 影响范围

### 4.1 破坏性变更
- ❌ 内部 hotspot-agent 进程被外部 AI Agent 替代
- ❌ 异步任务队列移除，写操作改同步直返
- ❌ heartbeat / watchdog 机制移除
- ❌ 内部 LLM 调用移除（extract / analyze 走外部 Agent）
- ❌ `/agent` Web 路由移除

### 4.2 兼容性
- ✅ SQLite 数据 100% 兼容
- ✅ 已有 favorites 数据保留（created_via 默认 'ui'）
- ✅ 已有 knowledge items / concepts 保留
- ✅ Phase 1-6 features 不受影响

### 4.3 性能
- 读 MCP tool: P50 < 100ms, P95 < 500ms
- 写 MCP tool: P95 < 100ms（同步直返）
- stdio 启动: < 1s
- SSE 握手: < 500ms
- tools/list: < 50ms

## 5. 回滚方案（如需）

紧急回滚到 v1.7.5：
1. 恢复 5 张 Phase 5 表（snapshot 还原）
2. 恢复 agent/ 目录（git checkout 8e7b939~1 -- agent/ backend/services/agent_*）
3. 关闭 feature.mcp_server，启用旧 feature_agent
4. 重启 hotspot

## 6. 验收门禁

完整 86 项 checklist: [phase7-mcp-server/checklist.md](../.trae/specs/phase7-mcp-server/checklist.md)
