-- 032_v1.7_kv_cache.sql: Phase 5 KV 缓存层
-- PRD §3.2.11
-- 注意: Phase 1 提前建表, 供后续 Phase 5 使用

CREATE TABLE IF NOT EXISTS kv_cache (
    key          TEXT PRIMARY KEY,
    value        TEXT NOT NULL,
    expires_at   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_kv_cache_expires ON kv_cache(expires_at);
