-- 024_v1.7_tags.sql: Phase 1 标签层级表 + hotspot_tags 多对多
-- PRD §3.2.1 / §6.2

CREATE TABLE IF NOT EXISTS tags (
    id        TEXT PRIMARY KEY,
    label     TEXT NOT NULL,
    type      TEXT NOT NULL,
    parent_id TEXT REFERENCES tags(id),
    weight    REAL DEFAULT 1.0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tags_type ON tags(type);
CREATE INDEX IF NOT EXISTS idx_tags_parent ON tags(parent_id);

CREATE TABLE IF NOT EXISTS hotspot_tags (
    hotspot_id TEXT NOT NULL REFERENCES hotspots(id) ON DELETE CASCADE,
    tag_id     TEXT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    confidence REAL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    PRIMARY KEY (hotspot_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_hotspot_tags_tag ON hotspot_tags(tag_id);
