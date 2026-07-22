-- 025_v1.7_reading_states.sql: Phase 1 阅读状态追踪
-- PRD §3.2.5

CREATE TABLE IF NOT EXISTS reading_states (
    entity_type  TEXT NOT NULL,
    entity_id    TEXT NOT NULL,
    opened_count INTEGER DEFAULT 0,
    dwell_ms     INTEGER DEFAULT 0,
    last_read_at TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (entity_type, entity_id)
);
CREATE INDEX IF NOT EXISTS idx_reading_states_last_read ON reading_states(last_read_at);
