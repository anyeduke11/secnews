-- v0.7 Batch ④: 阈值告警 — observability_alerts 表 + cooldown_until 唯一索引
-- 与 migration 081 的 api_events / api_metrics_hourly 配合, threshold_check_job
-- 写入 breach 记录; 前端 dashboard 顶部活跃横幅 + StatusBar 角标读这表.
CREATE TABLE IF NOT EXISTS observability_alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    level           TEXT    NOT NULL,             -- 'warn' | 'critical'
    metric          TEXT    NOT NULL,             -- 'api.error_rate_pct' | 'api.p95_latency_ms' | 'llm.error_rate_pct' | 'job.failure_rate_pct' | 'audit.llm_config_change_per_hour'
    value           REAL    NOT NULL,
    threshold       REAL    NOT NULL,
    window_minutes  INTEGER NOT NULL,
    detail          TEXT,                         -- JSON 字符串, 来源 (path_template / job_type / model 等)
    fired_at        TEXT    NOT NULL,             -- ISO UTC
    cooldown_until  TEXT    NOT NULL,             -- 同 (metric, level) cooldown_minutes 内不重复触发
    acked           INTEGER NOT NULL DEFAULT 0,   -- 0 = 活跃, 1 = 已 ack
    acked_at        TEXT,
    acked_by        TEXT
);

CREATE INDEX IF NOT EXISTS idx_observability_alerts_fired_at
    ON observability_alerts (fired_at);

CREATE INDEX IF NOT EXISTS idx_observability_alerts_active
    ON observability_alerts (acked, fired_at);

CREATE INDEX IF NOT EXISTS idx_observability_alerts_metric
    ON observability_alerts (metric, level, fired_at);