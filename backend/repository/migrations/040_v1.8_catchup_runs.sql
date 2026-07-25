-- 040_v1.8_catchup_runs.sql
-- Phase 8: 追抓资讯历史表（独立于 collection_runs）
-- 用途: 记录每次 catchup 调用的参数 + 结果, 供 /api/catchup/status 展示
-- 不动 collection_runs (实时采集); 追抓是 read-only consumer

CREATE TABLE IF NOT EXISTS catchup_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    mode                TEXT    NOT NULL CHECK (mode IN ('auto', 'manual')),
    since_window        TEXT    NOT NULL,        -- ISO 8601 UTC
    until_window        TEXT,                    -- ISO 8601 UTC, nullable (= now)
    categories          TEXT    NOT NULL,        -- JSON array, e.g. '["ai","security"]'
    max_per_source      INTEGER NOT NULL DEFAULT 20,
    started_at          TEXT    NOT NULL,
    finished_at         TEXT,                    -- ISO 8601 UTC, nullable
    status              TEXT    NOT NULL CHECK (status IN ('running','success','partial','failed','aborted')),
    items_ingested      INTEGER NOT NULL DEFAULT 0,
    items_skipped       INTEGER NOT NULL DEFAULT 0,
    sources_attempted   INTEGER NOT NULL DEFAULT 0,
    sources_succeeded   INTEGER NOT NULL DEFAULT 0,
    error_msg           TEXT,
    duration_ms         INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_catchup_status  ON catchup_runs(status, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_catchup_started ON catchup_runs(started_at DESC);
