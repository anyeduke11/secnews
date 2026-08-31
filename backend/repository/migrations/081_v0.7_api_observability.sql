-- 081_v0.7_api_observability.sql
-- v0.7 Batch ③: TraceIDMiddleware 落表 (PRD §5.3, §7 ②).
--
-- 缺口 (从 080_v0.7_observability_tables.sql 注释继承):
--   TraceIDMiddleware 已在 dispatch 收尾发 api_request / api_response log_event
--   (文件 logger), 但不入 SQL — 不可聚合 / 不可查询. 本批补两张表 + record_api_call
--   helper + observability_aggregator_job (60min roll-up).
--
-- 设计:
--   - api_events 单条落库, 每次响应 1 行, TTL 7d (observability_ttl_job 扩)
--   - api_metrics_hourly 聚合预计算, TTL 30d (observability_ttl_job 扩)
--   - 路径用 path_template (FastAPI route.path, 如 /api/llm/status/{id}),
--     不是 raw URL (含 query string 会维度爆炸)
--   - 异常路径 status=500 + error=异常名, 与正常路径同一张表便于统一查询

CREATE TABLE IF NOT EXISTS api_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id      TEXT    NOT NULL,                  -- UUIDv4 hex (middleware 注入)
    method        TEXT    NOT NULL,                  -- GET/POST/PUT/DELETE (uppercase)
    path_template TEXT    NOT NULL,                  -- FastAPI 路由模板
    status        INTEGER NOT NULL,                  -- HTTP 响应码 (含 5xx 异常路径)
    duration_ms   INTEGER NOT NULL,
    error         TEXT,                              -- 异常摘要[:500], 仅 5xx 填
    occurred_at   TEXT    NOT NULL                   -- ISO-8601 UTC
);
CREATE INDEX IF NOT EXISTS idx_api_events_occurred_at
  ON api_events (occurred_at);
CREATE INDEX IF NOT EXISTS idx_api_events_path_at
  ON api_events (path_template, occurred_at);
CREATE INDEX IF NOT EXISTS idx_api_events_trace
  ON api_events (trace_id);
CREATE INDEX IF NOT EXISTS idx_api_events_status_at
  ON api_events (status, occurred_at);

CREATE TABLE IF NOT EXISTS api_metrics_hourly (
    hour          TEXT    NOT NULL,                  -- 'YYYY-MM-DDTHH' (UTC)
    path_template TEXT    NOT NULL,
    total         INTEGER NOT NULL,
    errors        INTEGER NOT NULL,                  -- 5xx 计数
    p50_ms        INTEGER NOT NULL,
    p95_ms        INTEGER NOT NULL,
    max_ms        INTEGER NOT NULL,
    PRIMARY KEY (hour, path_template)
);
CREATE INDEX IF NOT EXISTS idx_api_metrics_hourly_hour
  ON api_metrics_hourly (hour);