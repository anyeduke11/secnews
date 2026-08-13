-- 052_v1.7_llm_cache.sql
-- Phase 16: LLM 缓存 + 用量日志表
-- 用于 LLMService 的缓存和成本监控

-- 1. LLM 缓存表
CREATE TABLE IF NOT EXISTS llm_cache (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cache_key       TEXT NOT NULL UNIQUE,
    provider        TEXT NOT NULL,
    model           TEXT NOT NULL,
    response        TEXT NOT NULL,
    cached_at       TEXT NOT NULL,
    ttl_seconds     INTEGER NOT NULL DEFAULT 86400
);

CREATE INDEX IF NOT EXISTS idx_llm_cache_key ON llm_cache(cache_key);
CREATE INDEX IF NOT EXISTS idx_llm_cache_expiry ON llm_cache(cached_at, ttl_seconds);

-- 2. LLM 用量日志表
CREATE TABLE IF NOT EXISTS llm_usage_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    provider        TEXT NOT NULL,
    model           TEXT NOT NULL,
    task            TEXT NOT NULL,          -- 'score' | 'summarize' | 'extract_entities' | 'generate'
    tokens          INTEGER NOT NULL DEFAULT 0,
    cost_usd        REAL NOT NULL DEFAULT 0.0,
    latency_ms      INTEGER NOT NULL DEFAULT 0,
    occurred_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_llm_usage_provider ON llm_usage_log(provider, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_usage_task ON llm_usage_log(task, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_usage_cost ON llm_usage_log(occurred_at);