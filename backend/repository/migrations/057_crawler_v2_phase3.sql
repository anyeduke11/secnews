-- Phase 3: 源级调度 + 健康管理 — 健康状态机 + 告警表
-- 来源: docs/crawler-v2-technical-spec.md §3.1 + §3.9
-- 依赖: 055_crawler_v2_phase0.sql (crawler_sources 表)

-- ============================================================
-- 1. 源告警记录表
-- ============================================================
CREATE TABLE IF NOT EXISTS source_alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       TEXT NOT NULL,                     -- crawler_sources.id
    alert_type      TEXT NOT NULL,                     -- 'consecutive_failure' | 'rejection_rate' | 'http_status' | 'duration' | 'url_check' | 'p0_dead'
    level           TEXT NOT NULL DEFAULT 'P2',        -- 'P1' | 'P2'
    message         TEXT NOT NULL,                     -- 告警描述
    detail          TEXT DEFAULT '',                   -- JSON 详情
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_sa_source_id ON source_alerts(source_id);
CREATE INDEX IF NOT EXISTS idx_sa_alert_type ON source_alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_sa_created_at ON source_alerts(created_at);
CREATE INDEX IF NOT EXISTS idx_sa_level ON source_alerts(level);

-- ============================================================
-- 2. crawler_sources 补充字段 — grace 观察期计数
-- ============================================================
ALTER TABLE crawler_sources ADD COLUMN grace_rounds INTEGER NOT NULL DEFAULT 0;