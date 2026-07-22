-- 026_v1.7_sm2_reviews.sql: Phase 2 SM-2 间隔复习
-- PRD §3.2.6 / §6.9
-- 注意: Phase 1 提前建表, 供 Task 1.2b ReadingState 复用基础设施

CREATE TABLE IF NOT EXISTS sm2_reviews (
    id           TEXT PRIMARY KEY,
    entity_type  TEXT NOT NULL,
    entity_id    TEXT NOT NULL,
    easiness     REAL DEFAULT 2.5,
    interval     INTEGER DEFAULT 0,
    repetitions  INTEGER DEFAULT 0,
    due_at       TEXT NOT NULL,
    last_grade   INTEGER,
    last_reviewed_at TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sm2_due ON sm2_reviews(due_at);
CREATE INDEX IF NOT EXISTS idx_sm2_entity ON sm2_reviews(entity_type, entity_id);
