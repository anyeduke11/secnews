-- v0.7 Batch ⑤: 用户显式反馈事件表 (like/dislike).

CREATE TABLE IF NOT EXISTS feedback_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,      -- hotspot | knowledge
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,           -- like | dislike
    signal REAL NOT NULL,
    category TEXT,
    source TEXT,
    tags TEXT,                      -- JSON 数组
    title TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_feedback_entity
    ON feedback_events(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_feedback_created
    ON feedback_events(created_at DESC);
