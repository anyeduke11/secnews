# Phase 7 — MCP Server 集成指南

> **版本**: v1.7.6
> **日期**: 2026-07-25
> **目的**: 让任意外部 AI Agent (Cursor / Claude Desktop / Trae / Workbuddy) 通过标准 MCP 协议读写 hotspot 知识库

---

## 1. 概述

hotspot v1.7.6 引入 **MCP (Model Context Protocol) Server**。LLM 推理全部在外部 AI Agent 侧执行，hotspot 只做**数据存储 + 本地规则提取 + 9 个 MCP 工具暴露**。

### 1.1 核心原则

- **零状态**: hotspot 不维护 session / heartbeat / watchdog
- **同步直返**: 9 个 MCP tool 全部同步直接返回（5 读 + 4 写）
- **数据与智能分离**: hotspot 暴露数据 + 工具；LLM 推理由外部 AI Agent 承担
- **本地优先**: 默认绑定 127.0.0.1，避免远程攻击

### 1.2 性能预期

| 指标 | 目标 |
|------|------|
| MCP tool 读 | P50 < 100ms, P95 < 500ms |
| MCP tool 写 | 同步直返, P95 < 100ms |
| stdio transport 启动 | < 1s |
| SSE transport 握手 | < 500ms |
| `tools/list` 响应 | < 50ms |

### 1.3 限制说明

- **绑定地址**: 默认 `127.0.0.1:8000`；改 `0.0.0.0` 需手动改 config + warning log
- **单用户**: 不支持多用户/权限隔离
- **LLM 推理**: 不在 hotspot 侧，全部由外部 AI Agent 承担
- **写并发**: SQLite WAL + last_writer_wins，不维护 session 锁

---

## 2. 4 个 AI Agent 配置示例

### 2.1 Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
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

### 2.2 Trae

`~/.trae/mcp_config.json`:

```json
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

### 2.3 Cursor

`~/.cursor/mcp.json`:

```json
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

### 2.4 Workbuddy / 其他支持 SSE 的 Agent

```json
{
  "mcpServers": {
    "hotspot": {
      "url": "http://127.0.0.1:8000/mcp/sse"
    }
  }
}
```

**前提**: hotspot 已启动 (`python run.py`)，且 `feature.mcp_server` flag 为 `True`（默认开启）。

---

## 3. 9 个 MCP Tool 详细说明

### 3.1 读操作（5 个）

#### `search_hotspots` — 搜索热点

**输入**:
```json
{
  "q": "fastapi",          // 搜索关键词
  "tags": ["ai"],          // 可选, tag 筛选
  "tag_mode": "any",       // "any" | "all"
  "time_range": "D7",      // "D7" | "H24" | "D3"
  "limit": 20              // 默认 20
}
```

**输出**: `{items: [{id, title, summary, source, ...}]}`

**典型场景**: AI Agent 拿到用户问题后，调此工具找匹配的热点。

---

#### `get_hotspot` — 获取单个热点详情

**输入**: `{hotspot_id: "abc123"}`

**输出**: `{item: {id, title, summary, content, tags, source, ...}}`

**典型场景**: 拿到 search_hotspots 列表后，深入读某条。

---

#### `list_favorites` — 列出收藏

**输入**:
```json
{
  "limit": 50,
  "cursor": null           // 分页 cursor (可选)
}
```

**输出**: `{favorites: [{hotspot_id, title, source, url, favorited_at, created_via}]}`

**典型场景**: AI Agent 读用户收藏，理解用户兴趣。

---

#### `search_knowledge` — 搜索知识条目

**输入**:
```json
{
  "q": "transformer",
  "lifecycle": "amplify:tagged",   // 可选过滤
  "limit": 30
}
```

**输出**: `{items: [{id, title, domain, topic, tags, lifecycle, ...}]}`

**典型场景**: AI Agent 查 hotspot 之外的概念/学习条目。

---

#### `get_personal_profile` — 获取个人画像

**输入**: `{}`

**输出**:
```json
{
  "version": "1.7.0",
  "total": 42,
  "profile": [
    {"key": "category:ai", "weight": 0.85, "last_updated": "..."},
    {"key": "tag:fastapi", "weight": 0.62, "last_updated": "..."}
  ]
}
```

**典型场景**: AI Agent 根据画像定制响应（推荐高权重主题）。

---

### 3.2 写操作（4 个）

#### `add_favorite` — 添加收藏

**输入**:
```json
{
  "hotspot_id": "abc123",
  "note": "LLM 视角的推荐"     // 可选备注
}
```

**输出**:
```json
{
  "success": true,
  "item_id": 42,
  "created_via": "mcp"      // 自动设为 mcp
}
```

**典型场景**: AI Agent 觉得某条重要，代替用户收藏。

---

#### `remove_favorite` — 取消收藏

**输入**: `{hotspot_id: "abc123"}`

**输出**: `{success: true}`

---

#### `add_annotation` — 添加标注

**输入**:
```json
{
  "entity_type": "hotspot",   // "hotspot" | "knowledge_item"
  "entity_id": "abc123",
  "content": "AI 评论..."
}
```

**输出**: `{success: true, annotation_id: 99}`

---

#### `update_knowledge_item` — 更新知识条目

**输入**:
```json
{
  "item_id": "cubox-abc123",
  "fields": {
    "tags": ["ai", "fastapi"],
    "concepts": ["transformer"],
    "lifecycle": "amplify:tagged"
  }
}
```

**输出**: `{success: true}`

**典型场景**: AI Agent 调 LLM 提取深度标签后，回写。

---

## 4. 双 Transport 详解

### 4.1 stdio（默认，推荐）

- **启动**: `python -m backend.mcp_stdio_main`
- **协议**: JSON-RPC 2.0 over stdin/stdout
- **适用**: 本地 AI Agent (Claude Desktop / Trae / Cursor)
- **生命周期**: 由 AI Agent 进程管理 (spawn / kill)

### 4.2 SSE / StreamableHTTP

- **端点**: `http://127.0.0.1:8000/mcp/sse`
- **协议**: Server-Sent Events over HTTP
- **适用**: 远程调试、跨网络（需改 host 为 0.0.0.0 + warning）
- **生命周期**: 长连接

---

## 5. 验证

### 5.1 启动后检查

```bash
# 1. 启动 hotspot
python run.py

# 2. 访问 MCP 状态端点
curl http://127.0.0.1:8000/api/mcp/status
# 应返回: {"enabled": true, "transport": "sse", "tools_count": 9, ...}

# 3. 列出 9 个 tool
curl http://127.0.0.1:8000/api/mcp/tools

# 4. 测试 stdio
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python -m backend.mcp_stdio_main
```

### 5.2 配置检查

在 Settings 抽屉的「MCP Server」卡片：
- 启用 toggle 应为 ON（绿色）
- 显示 5 读 + 4 写 = 9 个 tool
- 点击「复制 stdio 配置」可粘贴到 AI Agent 的 settings.json

---

## 6. 故障排查

| 现象 | 原因 | 解决 |
|------|------|------|
| AI Agent 找不到 hotspot server | stdio 路径错 | 检查 `cwd` 是否为 `/Users/duke/Documents/hotspot` |
| `/api/mcp/status` 返回 503 | `feature.mcp_server=False` | 改 `config.py` + 重启 |
| `tools/list` 返回 0 tools | seeding 未跑 | 重启 hotspot, lifespan 自动 seed |
| 写入后 favorites 表没记录 | transaction 失败 | 检查 SQLite WAL 文件权限 |
| `mark_digest_read` 返回 404 | digest_id 不存在 | 查 `/api/digests` 列表确认 ID |
