-- 027_v1.7_annotations.sql: Phase 2 笔记/标注空间
-- PRD §3.2.7 / §6.12
-- 注意: Phase 1 提前建表, 供后续 Phase 2 使用

CREATE TABLE IF NOT EXISTS annotations (
    id           TEXT PRIMARY KEY,
    entity_type  TEXT NOT NULL,
    entity_id    TEXT NOT NULL,
    content      TEXT NOT NULL,
    range_start  INTEGER,
    range_end    INTEGER,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_annotations_entity ON annotations(entity_type, entity_id);
