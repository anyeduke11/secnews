# Phase 7 — MCP Server（hotspot ↔ 外部 AI Agent 通过 MCP 通信）

> **版本**: v1.7.6 (Option A 简化版)
> **日期**: 2026-07-25
> **spec 路径**: `.trae/specs/phase7-mcp-server/`
> **PRD 章节**: [hotspot_v1.7_PRD.md §16](file:///Users/duke/Documents/hotspot/docs/hotspot_v1.7_PRD.md)
> **前置**: v1.7.5 Phase 1-6 全部完成 (commits 102730d / 739f98f / 3f19f3a / 53be5ad / a8e12fd / 935deed / b8e6fac / f4990b1)

## 1. 目标

hotspot v1.7.6 引入 **MCP (Model Context Protocol) Server**，让任意外部 AI Agent（Cursor / Claude Desktop / Trae / Workbuddy / Claude Code / 自定义）通过标准 MCP 协议**直接同步读写**本地知识库。LLM 推理全部在外部 AI Agent 侧执行，hotspot 只做**数据存储 + 本地规则提取 + MCP 工具暴露**。

### 1.1 核心原则（MCP-First / Option A）

1. **零状态**：hotspot 不维护 session / heartbeat / watchdog；MCP server 零状态
2. **同步直返**：MCP tool 调用全部同步直接返回（读 5 + 写 8），无内部队列
3. **数据与智能分离**：hotspot 暴露数据 + 工具；LLM 推理由外部 AI Agent 承担
4. **复用 FastAPI 端点**：通过 fastapi-mcp 把已有 /api/* 端点自动暴露为 MCP tool，不重写业务逻辑
5. **本地优先**：默认绑定 127.0.0.1，避免远程攻击

### 1.2 关键变化（与 v1.7.5 Phase 5 对比）

| 维度 | v1.7.5 (Phase 5 内部 hotspot-agent) | v1.7.6 (Phase 7 Option A: MCP) |
|------|-------------------------------------|-------------------------------|
| Agent 进程 | hotspot 自带 `agent/cli.py` | 外部 Cursor/Claude Desktop 等 |
| 通信协议 | 自定义 HTTP + JSON | 标准 MCP (JSON-RPC) |
| 任务队列 | knowledge_tasks 队列 + 文件系统 | **无（同步直返）** |
| 心跳 / 看门狗 | heartbeat + watchdog | **无** |
| LLM 推理 | hotspot-agent 内调 Anthropic SDK | 外部 AI Agent（用户自选模型）|
| 写延迟 | 入队 < 50ms, 执行在 agent 轮询周期后 | 同步直返 < 100ms (P95) |
| 状态复杂度 | agent 进程 + 队列 + heartbeat | 零状态 |
| **删除的代码** | - | `agent/` 目录 / `agent_task_service.py` / `agent_protocol.py` / `kv_cache_service.py` / knowledge_tasks 表 / agent_heartbeats 表 / skill_config 表 / mcp_tool_invocations 表 / `/agent` 路由 + 5 tab 组件 |

## 2. 范围

### 2.1 必做（Phase 7 内交付）

**MCP 基础设施**
- `fastapi-mcp` 库集成（依赖 + lifespan 注册 + stdio 入口）
- `mcp_tool_registry` 表 + 启动 seeding（13 个 tool 元数据）
- 双 transport：stdio（默认）+ SSE（http://127.0.0.1:8000/mcp/sse）

**13 个 MCP Tool**（5 读 + 8 写，全部同步直返）
- 读: `search_hotspots` / `get_hotspot` / `list_favorites` / `search_knowledge` / `get_personal_profile`
- 写: `add_favorite` / `remove_favorite` / `add_annotation` / `update_knowledge_item` / `trigger_extract_tags` / `trigger_cubox_sync` / `create_alert_rule` / `mark_digest_read`

**Phase 5 清理（Option A 关键）**
- DROP 5 张 Phase 5 表: `knowledge_tasks` / `agent_heartbeats` / `agent_task_skills` / `skill_config` / `mcp_tool_invocations`
- ALTER `favorites` ADD COLUMN `created_via` (enum: 'ui' / 'mcp' / 'agent')
- 删除 `agent/` 目录 + 4 个 service 文件 + `/api/agent/*` 端点（除 4 个 deprecated 保留）
- 删除 5 个 Phase 5 调度器 job: `agent_task_consumer` / `agent_heartbeat_check` / `kv_cache_cleanup` / `auto_extract_llm` / `review_scheduler_llm`
- 清空 `knowledge/learning/tasks/{pending,processing}/` 目录

**前端设置卡片**
- `<MCPSettingsCard />`（SettingsPage 内嵌）：MCP endpoint + 13 tool 列表 + 复制配置
- 路由 `/settings/mcp`
- Feature flag `mcp_server` toggle UI

**测试与文档**
- 8 个后端测试文件（unit + integration + e2e）
- 1 个前端组件测试
- 4 个文档（mcp_integration / mcp_vs_phase5 / phase7_changelog / mcp_tools_schema）

### 2.2 明确不做（推迟或保持不变）

- ❌ 内部 hotspot-agent 进程（由外部 AI Agent 替代）
- ❌ knowledge_tasks 异步队列（写操作直接落库）
- ❌ heartbeat / watchdog 机制
- ❌ 内部 LLM 调用（extract / analyze 走外部 Agent）
- ❌ Web 设置面板 `/agent` 路由（MCP 配置在 AI Agent 的 settings.json）
- ❌ MCP 远程访问（默认 127.0.0.1，0.0.0.0 需手动 + warning log）
- ✅ `kv_cache` 表保留为可选加速层（不主动维护，不在 038 删除范围）
- ✅ Phase 5 4 个 deprecated `/api/agent/*` 端点保留（tasks / complete / status / knowledge），供内部/调试用

## 3. 数据模型

### 3.1 新增表（1 张）

**Migration 037: `037_v1.7_mcp_tool_registry.sql`**

```sql
CREATE TABLE mcp_tool_registry (
    name           TEXT PRIMARY KEY,        -- e.g. "search_hotspots"
    category       TEXT NOT NULL,            -- 'read' | 'write'
    description    TEXT NOT NULL,
    input_schema   TEXT NOT NULL,            -- JSON Schema (UTF-8)
    enabled        INTEGER DEFAULT 1,        -- 0 | 1
    version        TEXT DEFAULT '2025-06-18', -- MCP spec version
    created_at     TEXT NOT NULL
);

CREATE INDEX idx_mcp_tool_category ON mcp_tool_registry(category);
CREATE INDEX idx_mcp_tool_enabled ON mcp_tool_registry(enabled);
```

**用途**: tools/list 端点返回工具元数据 + SettingsPage 展示可用工具。**不记录调用日志**（走 server log）。

### 3.2 现有表修改（1 张）

**Migration 039: `039_v1.7_add_favorite_source.sql`**

```sql
ALTER TABLE favorites ADD COLUMN created_via TEXT NOT NULL DEFAULT 'ui'
    CHECK (created_via IN ('ui', 'mcp', 'agent'));
```

**用途**: 区分收藏来源，统计和调试。MCP tool `add_favorite` 写入时设 `created_via='mcp'`。

### 3.3 删除表（5 张，Phase 5 引入 Option A 不再需要）

**Migration 038: `038_v1.7_drop_phase5_tables.sql`**

```sql
DROP TABLE IF EXISTS knowledge_tasks;
DROP TABLE IF EXISTS agent_heartbeats;
DROP TABLE IF EXISTS agent_task_skills;
DROP TABLE IF EXISTS skill_config;
DROP TABLE IF EXISTS mcp_tool_invocations;
-- kv_cache 评估后保留为可选加速层（不主动维护）
```

**审计要求**:
- DROP 前必须确认 `knowledge_tasks` 队列内容仅是 hot_take_collect + 一些遗留 task-XXX.md，全部可清理
- DROP 后保留 7 天快照（如 `backend/data/dropped_tables_snapshot_2026-07-25.sql`）

### 3.4 数据关系

```
mcp_tool_registry (启动 seeding, 不跨端)
    └─ 13 个 tool 的元数据
    └─ SettingsPage MCPSettingsCard 展示

favorites.created_via (enum: 'ui' / 'mcp' / 'agent')
    └─ 区分收藏来源

[已删除] knowledge_tasks (Phase 7 DROP)
[已删除] agent_heartbeats
[已删除] agent_task_skills
[已删除] skill_config
[已删除] mcp_tool_invocations
```

## 4. MCP Tool 设计（13 个）

### 4.1 读操作（5 个，sync 直返）

| Tool 名称 | 输入 (JSON Schema 摘要) | 输出 | 路由 FastAPI |
|----------|------------------------|------|-------------|
| `search_hotspots` | `{q, tags?, tag_mode?, time_range?, limit?}` | `{items: [...]}` | `GET /api/hotspots` |
| `get_hotspot` | `{hotspot_id}` | `{hotspot: {...}}` | `GET /api/hotspots/{id}` |
| `list_favorites` | `{limit?, cursor?}` | `{favorites: [...]}` | `GET /api/favorites` |
| `search_knowledge` | `{q, lifecycle?, limit?}` | `{items: [...]}` | `GET /api/knowledge/items` |
| `get_personal_profile` | `{}` | `{profile: {...}}` | `GET /api/profile` |

### 4.2 写操作（8 个，sync 直返）

| Tool 名称 | 输入 (JSON Schema 摘要) | 输出 | 路由 FastAPI |
|----------|------------------------|------|-------------|
| `add_favorite` | `{hotspot_id, note?}` | `{success, item_id, created_via}` | `POST /api/favorites` |
| `remove_favorite` | `{hotspot_id}` | `{success}` | `DELETE /api/favorites/{id}` |
| `add_annotation` | `{entity_type, entity_id, content}` | `{success, annotation_id}` | `POST /api/annotations` |
| `update_knowledge_item` | `{item_id, fields: {...}}` | `{success}` | `PATCH /api/knowledge/items/{id}` |
| `trigger_extract_tags` | `{hotspot_id}` | `{success, tags: [...]}` | `POST /api/extract/auto` (本地规则, 无 LLM) |
| `trigger_cubox_sync` | `{target_path?, format?}` | `{success, count}` | `POST /api/cubox/sync` (本地 CLI) |
| `create_alert_rule` | `{rule: {...}}` | `{success, rule_id}` | `POST /api/alerts/rules` |
| `mark_digest_read` | `{digest_id}` | `{success}` | `POST /api/digests/{id}/read` |

### 4.3 LLM 推理责任划分

**关键决策**: LLM 推理在外部 AI Agent 侧，hotspot 不调任何 LLM。

```
AI Agent 调 trigger_extract_tags (本地规则, 无 LLM):
  触发 → hotspot 用本地规则 + 关键词提取 (Phase 1 已实现, 置信度 0.5-1.0)
       → 返回 {tags: ["ai-security", "langchain"], confidence: 0.7}
  适用场景: 快速、低成本、不需要深度理解

AI Agent 自己用 LLM 提取 (高级):
  AI Agent 先调 get_hotspot({hotspot_id}) 拿全文
  → AI Agent 在 LLM 上下文中分析
  → AI Agent 调 update_knowledge_item({item_id, fields: {tags: [...]}})
  适用场景: 需要深度语义理解, 用户接受 LLM 调用成本
```

**hotspot 不做的事**:
- ❌ 调 LLM (Anthropic / OpenAI / Gemini)
- ❌ 维护 agent runtime
- ❌ 维护 session 状态
- ❌ heartbeat / watchdog

**hotspot 做的事**:
- ✅ 暴露 MCP tool (13 个)
- ✅ SQLite 读写
- ✅ .md 文件读写
- ✅ 本地规则提取 (无 LLM)
- ✅ cubox-cli 调用 (无 LLM)
- ✅ FTS5 搜索

### 4.4 fastapi-mcp 集成示例

```python
# backend/api/mcp_config.py
from fastapi_mcp import FastApiMCP
from backend.main import app

mcp = FastApiMCP(
    app,
    name="hotspot",
    description="Hotspot Knowledge MCP Server — 让 AI Agent 读写本地知识库",
    base_url="http://127.0.0.1:8000",
    include_operations=[
        # 读: 5 个
        "list_hotspots_api_hotspots_get",
        "get_hotspot_api_hotspots__id__get",
        "list_favorites_api_favorites_get",
        "search_knowledge_api_knowledge_items_get",
        "get_profile_api_profile_get",
        # 写: 8 个
        "add_favorite_api_favorites_post",
        "remove_favorite_api_favorites__id__delete",
        "add_annotation_api_annotations_post",
        "update_knowledge_item_api_knowledge_items__id__patch",
        "trigger_extract_tags_api_extract_auto_post",
        "trigger_cubox_sync_api_cubox_sync_post",
        "create_alert_rule_api_alerts_rules_post",
        "mark_digest_read_api_digests__id__read_post",
    ],
)

# 启动 SSE 端点 (同 FastAPI 端口)
mcp.mount_sse_endpoint(path="/mcp/sse")

# stdio 入口: $ python -m backend.mcp_stdio_main
```

## 5. 双 Transport 支持

### 5.1 stdio（默认，本地单进程）

```json
// Claude Desktop / Trae / Cursor 等的 settings.json
{
  "mcpServers": {
    "hotspot": {
      "command": "python",
      "args": ["-m", "backend.mcp_stdio_main"],
      "cwd": "/Users/duke/Documents/hotspot"
    }
  }
}
```

### 5.2 SSE / StreamableHTTP（HTTP, 跨网络, 本机调试用）

```json
{
  "mcpServers": {
    "hotspot": {
      "url": "http://127.0.0.1:8000/mcp/sse"
    }
  }
}
```

**前提**:
- hotspot 已启动 (`python run.py`)
- 默认绑定 `127.0.0.1:8000`，避免远程攻击
- `feature.mcp_server = on`（Option A 默认开启）

## 6. API 端点

### 6.1 MCP 调试端点（2 个，前缀 `/api/mcp`）

| Method | Path | 说明 | 状态码 |
|--------|------|------|--------|
| GET | `/api/mcp/status` | MCP server 状态（enabled, transport, tools_count） | 200 |
| GET | `/api/mcp/tools` | 列出 13 个 tool 的 name + description + input_schema | 200 |

> **移除** `/api/mcp/sessions` / `/api/mcp/test` / `/api/mcp/tool_invocations` —— Option A 不维护 session 状态, 调用日志走 server log。

### 6.2 Phase 5 端点降级

| Method | Path | 状态 | 原因 |
|--------|------|------|------|
| POST | `/api/agent/tasks` | 保留为 deprecated | 内部/调试用 |
| GET | `/api/agent/tasks` | 保留为 deprecated | 同上 |
| POST | `/api/agent/tasks/{id}/complete` | 保留为 deprecated | 同上 |
| GET | `/api/agent/tasks/{id}/status` | 保留为 deprecated | 同上 |
| POST | `/api/agent/start` | **删除** | 没有内部 agent 可启 |
| POST | `/api/agent/stop` | **删除** | 同上 |
| POST | `/api/agent/restart` | **删除** | 同上 |
| GET | `/api/agent/status` | **删除** | 同上 |
| GET | `/api/agent/heartbeat` | **删除** | 同上 |
| POST | `/api/agent/knowledge` | **删除** | AI Agent 调 `update_knowledge_item` 替代 |

**变更说明**: `/api/agent.py` 整体重写，仅保留 4 个 deprecated GET 端点作为迁移期兼容。

### 6.3 设置端点（1 个）

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/settings/mcp/config` | 返回 MCP 端点 + 13 tool 列表 + 复制配置 JSON 字符串 |
| PUT | `/api/settings/mcp/enabled` | 切换 `feature.mcp_server` 开关（重启后生效） |

## 7. 调度器变更

### 7.1 删除的 job（5 个）

| Job | 删除原因 |
|-----|---------|
| `agent_task_consumer` (60s) | 没有内部 agent 拉任务 |
| `agent_heartbeat_check` | 没有内部 agent 心跳 |
| `kv_cache_cleanup` (30min) | kv_cache 表保留但服务层不主动维护 |
| `auto_extract_llm` | LLM 在外部 agent，本地不做 |
| `review_scheduler_llm` | 同上 |

### 7.2 保留的 job（v1.7 全部 13 个 + v1.6 既有）

```
hot_take_collect        5min
auto_extract            触发式 (采集完成后, 本地规则)
review_scheduler        6h (仅查询, 评分用户在 UI 完成)
alert_evaluator         60s
profile_updater         30min
digest_generator        24h (08:00)
source_health_check     15min
fts_rebuild             5min
profile_decay           24h (03:00)
cubox_auto_sync         24h (03:00, 本地 CLI 调用, 无 LLM)
[v1.6 既有]  collection, sync, etc.
```

## 8. 前端组件

### 8.1 新增组件（1 个）

| 组件 | 路径 | 用途 |
|------|------|------|
| `<MCPSettingsCard />` | `components/settings/MCPSettingsCard.tsx` | 显示 MCP endpoint + 复制按钮 + 13 tool 列表 + enabled toggle |

### 8.2 删除的组件（Phase 5 引入, Option A 不再需要）

| 组件 | 删除原因 |
|------|---------|
| `<AgentStatusBadge />` | 没有内部 agent |
| `<AgentPage />` (含 5 tab) | 同上 |
| `<AgentOverviewTab />` 等 5 个 | 同上 |

### 8.3 设置面板 (`/settings`) 新增 MCP 一栏

```
┌──────────────────────────────────────────────┐
│  MCP Server (供 AI Agent 连接)                  │
│                                                │
│  ☑ 启用 MCP Server                             │
│                                                │
│  Transport:                                    │
│    ⦿ stdio (推荐, 本地进程)                     │
│    ◯ SSE (http://127.0.0.1:8000/mcp/sse)       │
│                                                │
│  ─── 在 AI Agent 中配置 (示例) ───              │
│                                                │
│  Claude Desktop / Trae:                        │
│  ┌──────────────────────────────────────────┐ │
│  │ {                                        │ │
│  │   "mcpServers": {                        │ │
│  │     "hotspot": {                         │ │
│  │       "command": "python",               │ │
│  │       "args": ["-m", "backend.mcp_stdio_main"], │ │
│  │       "cwd": "/Users/duke/Documents/hotspot" │ │
│  │     }                                    │ │
│  │   }                                      │ │
│  │ }                                        │ │
│  └──────────────────────────────────────────┘ │
│  [ 复制 ]                                       │
│                                                │
│  ─── 可用工具 (13 个) ───                      │
│  □ search_hotspots     □ get_hotspot          │
│  □ list_favorites      □ search_knowledge     │
│  □ get_personal_profile                       │
│  □ add_favorite        □ remove_favorite      │
│  □ add_annotation      □ update_knowledge_item│
│  □ trigger_extract_tags □ trigger_cubox_sync │
│  □ create_alert_rule   □ mark_digest_read     │
│                                                │
└──────────────────────────────────────────────┘
```

### 8.4 路由变更

| 路由 | 状态 | 原因 |
|------|------|------|
| `/agent` (含 5 tab) | **删除** | Option A 无内部 agent |
| `/settings/mcp` | **新增** | 展示 MCP endpoint + 复制按钮 |

## 9. 关键决策

1. **范围**: Option A 简化版（全量 §16 范围，无任何 Phase 5 残留）
2. **MCP 库选型**: `fastapi-mcp`（Anthropic 官方推荐，与 FastAPI 集成最简）
3. **MCP spec 版本**: 锁定 `2025-06-18`，覆盖 Cursor/Claude Desktop/Trae/Workbuddy
4. **Transport 双轨**: stdio（默认，推荐）+ SSE（HTTP 调试用）
5. **绑定地址**: 默认 `127.0.0.1:8000`；改 0.0.0.0 需 feature flag + warning log
6. **写操作同步直返**: 不再走异步队列（与 Phase 5 双轨设计相反）
7. **favorites.created_via**: 区分 'ui' / 'mcp' / 'agent'，跨端同步时合并
8. **mcp_tool_registry 启动 seeding**: 不跨端同步，新增 tool 需重启 hotspot
9. **kv_cache 评估后保留**: 不主动维护，schema 存在供未来按需启用
10. **Phase 5 agent 目录删除**: 整目录 + 4 service 文件 + `/agent` 路由 + 5 tab + 5 scheduler job
11. **deprecated 端点保留**: `/api/agent/{tasks, complete, status, knowledge}` 保留 4 个供内部调试
12. **测试策略**: 8 个后端测试文件 + 1 个前端测试 + 1 个 e2e（模拟 Cursor 调 MCP）

## 10. 性能验收

| 指标 | 目标 |
|------|------|
| MCP tool 读 | P50 < 100ms, P95 < 500ms |
| MCP tool 写 | 同步直返, P95 < 100ms |
| stdio transport 启动 | < 1s |
| SSE transport 握手 | < 500ms |
| Cubox 同步 (1000 卡片) | < 60s |
| `tools/list` 响应 | < 50ms (13 tool 元数据本地读 SQLite) |

## 11. 风险与对策

| # | 风险 | 概率 | 影响 | 对策 |
|---|------|------|------|------|
| 1 | fastapi-mcp 与现有中间件冲突 | 中 | 中 | 中间件测试矩阵; 准备手写 fallback |
| 2 | 外部 agent MCP 版本差异 | 中 | 中 | 锁定 MCP 2025-06-18 spec; 测试矩阵覆盖 Cursor/Claude Desktop/Trae/Workbuddy |
| 3 | 写并发冲突（多 agent 同改一条目）| 中 | 中 | SQLite WAL + last_writer_wins; 不维护 session; 写操作幂等 |
| 4 | 远程攻击面（0.0.0.0 监听）| 中 | 高 | 默认 127.0.0.1; feature flag + warning log |
| 5 | stdio 进程僵死 | 低 | 中 | 外部 agent 负责进程管理 (spawn / kill); hotspot 不负责 |
| 6 | MCP tool schema 升级破坏 agent | 中 | 中 | 工具版本号字段 (mcp_tool_registry.version) + 兼容层 |
| 7 | 删表迁移丢数据 | 低 | 高 | 迁移前 audit; knowledge_tasks 已知只含历史残留; 删除后保留 7 天快照 |
| 8 | fastapi-mcp 库升级 breaking | 中 | 中 | 锁版本 ≥ 0.4.0, < 1.0; 升级时跑 8 个测试套件 |

## 12. 验收标准（PRD §16.11 完整复刻）

| # | 门禁 |
|---|------|
| 1 | `python -m backend.mcp_stdio_main` 启动后, 列出 13 个 tool |
| 2 | Cursor / Claude Desktop 配置 hotspot MCP 后, AI 调 `search_hotspots` 返回结果 |
| 3 | AI 调 `add_favorite` 后, `favorites` 表新增 `created_via='mcp'` 记录, `knowledge/items/{id}.md` 已写入 |
| 4 | 多个 AI Agent (Cursor + Claude Desktop) 并发调, 无状态冲突 (无 session) |
| 5 | MCP server 默认绑定 127.0.0.1, 0.0.0.0 需 feature flag + warning |
| 6 | 删除的 5 张 Phase 5 表迁移可执行, 不影响现有数据 |
| 7 | 关闭 `feature.mcp_server` 后, MCP 端点返回 404 |
| 8 | e2e 链路: AI Agent 调 MCP → 落库 < 100ms (P95) |
| 9 | MCPSettingsCard 页面正确显示 13 个 tool, 复制配置可用 |

## 13. 与 Phase 1-6 的关系

| 维度 | Phase 1-6 (已完成) | Phase 7 (本 spec) |
|------|------------------|-------------------|
| 数据模型 | 13 张 v1.7 表 | +1 新增 (mcp_tool_registry) +1 改 (favorites.created_via) -5 删除 (Phase 5 表) |
| API | 38 router | +2 新增 (mcp/status + mcp/tools) +1 设置 (settings/mcp) -10 删除 (Phase 5 agent 端点, 保留 4 deprecated) |
| 调度器 | 13 v1.7 job + 既有 | -5 删除 (Phase 5 agent job) |
| 前端 | 30+ 组件 | +1 新增 (MCPSettingsCard) -7 删除 (AgentPage + 5 tab + Badge) |
| 同步 | 5 表 (sync_bundle v1.7) | 0 变化 (mcp_tool_registry 不跨端) |
| 文档 | Phase 1-6 报告 | +4 新增 (mcp_integration + mcp_vs_phase5 + phase7_changelog + mcp_tools_schema) |
| Agent | Phase 5 内部 hotspot-agent | **外部 AI Agent via MCP** |
| LLM 推理 | hotspot-agent 内调 | **外部 AI Agent 侧** |
