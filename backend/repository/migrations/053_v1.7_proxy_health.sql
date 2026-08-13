-- Phase 16: Crawl4ai 代理健康度日志表
-- 记录每个代理的 success/failure 事件，用于故障切换决策

CREATE TABLE IF NOT EXISTS proxy_health_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    proxy_url       TEXT NOT NULL,
    event           TEXT NOT NULL,        -- 'success' | 'failed' | 'timeout' | 'auth'
    source          TEXT DEFAULT '',       -- 哪个 collector 触发
    health_score    REAL DEFAULT 0.5,      -- 当前分数
    latency_ms      INTEGER DEFAULT 0,
    error_message   TEXT DEFAULT '',
    occurred_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_phl_proxy ON proxy_health_log(proxy_url, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_phl_event ON proxy_health_log(event, occurred_at DESC);