-- 028_v1.7_alert_rules.sql: Phase 3 告警规则与告警
-- PRD §3.2.8
-- 注意: Phase 1 提前建表, 供后续 Phase 3 使用

CREATE TABLE IF NOT EXISTS alert_rules (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    condition    TEXT NOT NULL,
    action       TEXT NOT NULL,
    cooldown_sec INTEGER DEFAULT 3600,
    enabled      INTEGER DEFAULT 1,
    last_fired_at TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id           TEXT PRIMARY KEY,
    rule_id      TEXT NOT NULL REFERENCES alert_rules(id) ON DELETE CASCADE,
    entity_type  TEXT,
    entity_id    TEXT,
    payload      TEXT,
    status       TEXT DEFAULT 'pending',
    created_at   TEXT NOT NULL,
    processed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
CREATE INDEX IF NOT EXISTS idx_alerts_rule ON alerts(rule_id);
