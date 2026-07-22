-- 031_v1.7_digests.sql: Phase 4 简报生成
-- PRD §3.2.10
-- 注意: Phase 1 提前建表, 供后续 Phase 4 使用

CREATE TABLE IF NOT EXISTS digests (
    id           TEXT PRIMARY KEY,
    period       TEXT NOT NULL,
    summary      TEXT NOT NULL,
    item_ids     TEXT DEFAULT '[]',
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_digests_period ON digests(period);
