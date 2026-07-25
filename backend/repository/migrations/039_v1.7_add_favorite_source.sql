-- 039_v1.7_add_favorite_source.sql
-- Phase 7: 添加 favorites.created_via 列区分收藏来源
-- 'ui' = hotspot UI 收藏
-- 'mcp' = 外部 AI Agent 通过 MCP tool 'add_favorite' 收藏
-- 'agent' = 内部 agent 收藏（已废弃，保留兼容）

ALTER TABLE favorites ADD COLUMN created_via TEXT NOT NULL DEFAULT 'ui'
    CHECK (created_via IN ('ui', 'mcp', 'agent'));

CREATE INDEX IF NOT EXISTS idx_favorites_created_via ON favorites(created_via);
