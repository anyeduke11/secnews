-- 037_v1.7_mcp_tool_registry.sql
-- Phase 7: MCP Server 工具注册表（启动时 seeding 13 个 tool 元数据）
-- 用途: tools/list 端点返回工具元数据 + SettingsPage 展示可用工具
-- 不记录调用日志（走 server log）

CREATE TABLE IF NOT EXISTS mcp_tool_registry (
    name           TEXT PRIMARY KEY,        -- e.g. "search_hotspots"
    category       TEXT NOT NULL,           -- 'read' | 'write'
    description    TEXT NOT NULL,
    input_schema   TEXT NOT NULL,           -- JSON Schema (UTF-8)
    enabled        INTEGER DEFAULT 1,       -- 0 | 1
    version        TEXT DEFAULT '2025-06-18', -- MCP spec version
    created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mcp_tool_category ON mcp_tool_registry(category);
CREATE INDEX IF NOT EXISTS idx_mcp_tool_enabled ON mcp_tool_registry(enabled);
