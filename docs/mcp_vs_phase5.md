# Phase 7 — MCP (Option A) vs Phase 5 内部 hotspot-agent 对比

> **版本**: v1.7.6
> **日期**: 2026-07-25
> **目的**: 解释为什么选择 Option A (外部 AI Agent via MCP) 而非 Phase 5 (内部 hotspot-agent)

---

## 1. 核心对比

| 维度 | Phase 5 内部 hotspot-agent (已弃) | Phase 7 Option A: MCP (采用) |
|------|-----------------------------------|-------------------------------|
| Agent 进程 | hotspot 自带 `agent/cli.py` | 外部 Cursor / Claude Desktop / Trae / Workbuddy |
| 通信协议 | 自定义 HTTP + JSON | **标准 MCP (JSON-RPC 2.0)** |
| 任务队列 | knowledge_tasks 队列 + 文件系统 | **无（同步直返）** |
| 心跳 / 看门狗 | heartbeat + watchdog | **无** |
| LLM 推理 | hotspot-agent 内调 Anthropic SDK | 外部 AI Agent（用户自选模型）|
| 写延迟 | 入队 < 50ms, 执行在 agent 轮询周期后 | **同步直返 < 100ms (P95)** |
| 状态复杂度 | agent 进程 + 队列 + heartbeat | **零状态** |
| 跨端同步 | 需同步 knowledge_tasks 队列 | **无需同步（无队列）** |
| 错误处理 | agent 进程崩溃需 watchdog 重启 | **无 agent 进程，自然无崩溃** |
| 用户选择模型 | 锁定 Anthropic SDK | **任意模型**（GPT-4 / Claude / Gemini / 本地 LLM）|

---

## 2. 为什么移除 Phase 5 组件

### 2.1 knowledge_tasks 队列

**Phase 5 设计**:
- hotspot 写 `knowledge_tasks` 表
- hotspot-agent 轮询拉取
- 执行后回写 DB + 移动文件

**Phase 7 删除原因**:
- 引入 60s 延迟（轮询周期）
- 需要复杂的任务状态机（pending → processing → done/failed）
- 文件系统 + DB 双重状态，需 sync
- 错误处理复杂（agent 进程崩溃 / 任务卡死）

**Phase 7 替代**:
- 同步直返，写操作立即落库
- AI Agent 调 `add_favorite` → SQLite INSERT → 返回 success < 100ms
- 无需任务队列

### 2.2 heartbeat / watchdog

**Phase 5 设计**:
- agent 每 30s 写 heartbeat
- hotspot 端 watchdog 检查超时，重启 agent
- agent_heartbeats 表

**Phase 7 删除原因**:
- 无内部 agent 进程，自然无心跳
- 外部 AI Agent 生命周期由用户管理（开 Claude Desktop / 关 Claude Desktop）

### 2.3 skill_config 表

**Phase 5 设计**:
- skill_config 存 LLM skill 配置（prompt template / model / secret 绑定）
- agent 启动时加载 skills

**Phase 7 删除原因**:
- LLM 推理在外部 agent 侧
- 外部 agent 用自己的 model config
- hotspot 不存 skill 配置

### 2.4 agent_task_service / kv_cache_service

**Phase 5 设计**:
- `agent_task_service`: 任务队列的 service 层封装
- `kv_cache_service`: LLM 调用结果缓存

**Phase 7 删除原因**:
- 任务队列已删除 → agent_task_service 无依赖
- LLM 推理已外移 → kv_cache 无意义（外部 agent 自己 cache）

---

## 3. 删除清单

### 3.1 删表（5 张）

| 表 | 原用途 | Phase 7 替代 |
|----|--------|-------------|
| `knowledge_tasks` | 任务队列 | 无（同步直返） |
| `agent_heartbeats` | agent 心跳 | 无（无 agent） |
| `agent_task_skills` | 任务 ↔ skill 关联 | 无（无 skill） |
| `skill_config` | LLM skill 配置 | 无（外部 LLM） |
| `mcp_tool_invocations` | Phase 5 MCP 调用日志 | 无（server log 已够） |

**保留**: `kv_cache` 表（不在删除范围，供未来按需启用）

### 3.2 删端点（10 个 → 保留 4 deprecated）

| 端点 | Phase 5 状态 | Phase 7 状态 |
|------|--------------|--------------|
| `POST /api/agent/tasks` | 创建任务 | 410 Gone |
| `POST /api/agent/tasks/{id}/complete` | 完成任务 | 410 Gone |
| `POST /api/agent/knowledge` | 写回知识 | 410 Gone |
| `POST /api/agent/start` | 启动 agent | **删除** |
| `POST /api/agent/stop` | 停止 agent | **删除** |
| `POST /api/agent/restart` | 重启 agent | **删除** |
| `GET /api/agent/status` | agent 状态 | **删除** |
| `GET /api/agent/heartbeat` | 心跳检查 | **删除** |
| `GET /api/agent/tasks` | 拉取任务 | 200 + 永远空 + deprecation |
| `GET /api/agent/tasks/{id}` | 查任务详情 | 410 Gone |
| `GET /api/agent/tasks/{id}/status` | 查任务状态 | 410 Gone |
| `GET /api/agent/knowledge` | 知识列表 | 200 + forwarded to /api/knowledge/items |

### 3.3 删调度器 job（2 个）

| Job | Phase 5 周期 | Phase 7 状态 |
|-----|--------------|--------------|
| `agent_task_consumer_job` | 60s | **删除** (无 agent 消费) |
| `kv_cache_cleanup_job` | 30min | 保留为 NoOp stub |

注: spec 列了 5 个 (含 `agent_heartbeat_check` / `auto_extract_llm` / `review_scheduler_llm`)，但这些在 codebase 中本就不存在。

### 3.4 删文件（5 个）

- `agent/` 整目录（cli.py / client.py / executor.py / poller.py / skills/）
- `backend/services/agent_task_service.py`
- `backend/services/kv_cache_service.py`
- `backend/services/skill_config_service.py`
- `backend/services/agent_protocol.py`（如存在）
- `backend/tests/test_agent_*.py` (5 个)
- `backend/tests/test_v1_7_e2e.py` (Phase 5 e2e)
- `backend/tests/test_kv_cache_service.py`

### 3.5 删 tasks 目录内容

- `knowledge/learning/tasks/pending/*.md` (5344 个 extract/compile/generate_learning_plan 任务)
- `knowledge/learning/tasks/processing/*.md` (空, 已清)

`done/` 和 `failed/` 保留作为历史归档。

### 3.6 Feature flag 切换

| Phase 5 | Phase 7 |
|---------|---------|
| `feature.agent = True` (默认) | `feature.mcp_server = True` (默认) |

注: `feature_agent` 在 config.py 中已删除（之前已迁移）。

---

## 4. 新增清单

### 4.1 新表（1 张）

`mcp_tool_registry` — 存 13 个 MCP tool 的元数据（name / category / description / input_schema / enabled / version）。启动 seeding，幂等。

### 4.2 改表（1 张）

`favorites` — 新增 `created_via TEXT NOT NULL DEFAULT 'ui' CHECK (created_via IN ('ui', 'mcp', 'agent'))`。

### 4.3 新增 MCP 工具

13 个（5 读 + 8 写），通过 fastapi-mcp 自动暴露。

### 4.4 新增 API 端点

| Method | Path | 用途 |
|--------|------|------|
| GET | `/api/mcp/status` | MCP 状态 |
| GET | `/api/mcp/tools` | 列出 13 个 tool |
| GET | `/api/settings/mcp/config` | 配置 + 复制 JSON |
| PUT | `/api/settings/mcp/enabled` | 切换开关 |

### 4.5 新增前端组件

`<MCPSettingsCard />` — 嵌入 Settings 抽屉，含 13 tool 列表 + 启用 toggle + 复制按钮。

### 4.6 新增入口

- `python -m backend.mcp_stdio_main` — stdio transport
- `http://127.0.0.1:8000/mcp/sse` — SSE transport

---

## 5. 迁移路径（从 Phase 5 升级到 Phase 7）

### 5.1 数据库迁移（自动）

启动 hotspot 时自动跑 migration 037/038/039：
1. 创建 `mcp_tool_registry` 表
2. 删除 5 张 Phase 5 表
3. 添加 `favorites.created_via` 列

### 5.2 旧代码清理（手动）

无 — Phase 7 已删除所有 Phase 5 代码。

### 5.3 旧 API 兼容

4 个 deprecated GET 端点保留 1-2 个版本，供内部/调试用：
- `GET /api/agent/tasks` — 返回空 + deprecation
- `GET /api/agent/tasks/{id}` — 410 Gone
- `GET /api/agent/tasks/{id}/status` — 410 Gone
- `GET /api/agent/knowledge` — 转发到 /api/knowledge/items

### 5.4 用户侧迁移

| Phase 5 用法 | Phase 7 替代 |
|--------------|--------------|
| 启动 hotspot-agent 进程 | 配置 Claude Desktop / Trae / Cursor |
| 调 `POST /api/agent/start` | 无需（AI Agent 自动启） |
| 等 heartbeat | 无需（外部 agent） |
| 调 `POST /api/agent/tasks/{id}/complete` | AI Agent 调 `add_favorite` 同步直返 |
| 看 `GET /api/agent/tasks` | AI Agent 调 `list_favorites` |

---

## 6. 风险评估

| # | 风险 | 概率 | 影响 | 对策 |
|---|------|------|------|------|
| 1 | fastapi-mcp 库升级 breaking | 中 | 中 | 锁版本 ≥ 0.4.0, < 1.0 |
| 2 | 外部 agent MCP 版本差异 | 中 | 中 | 锁定 MCP 2025-06-18 spec |
| 3 | 写并发冲突 | 中 | 中 | SQLite WAL + last_writer_wins |
| 4 | 远程攻击面 | 中 | 高 | 默认 127.0.0.1; 0.0.0.0 需 warning |
| 5 | stdio 进程僵死 | 低 | 中 | 外部 agent 负责 |
| 6 | 删表迁移丢数据 | 低 | 高 | 迁移前 audit + 7 天快照 |

---

## 7. 总结

Phase 7 Option A 是**简化、零状态、标准化**的选择：

- ✅ 简单: 13 个 tool，全部同步直返
- ✅ 灵活: 用户用任意 AI Agent
- ✅ 安全: 本地绑定，无远程攻击面
- ✅ 性能: 写 < 100ms, 读 < 500ms
- ✅ 互操作: 标准 MCP 协议，Cursor/Claude Desktop/Trae 都支持

vs Phase 5:

- ❌ 复杂: 任务队列 + heartbeat + watchdog + LLM 集成
- ❌ 锁定: 单一 LLM 供应商
- ❌ 状态: agent 进程 + 队列状态 + 心跳状态
- ❌ 延迟: 60s 轮询周期
- ❌ 风险: agent 进程崩溃、任务卡死、watchdog 误判
