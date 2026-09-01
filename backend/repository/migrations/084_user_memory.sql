-- v0.7 Batch ⑤: 用户记忆表 (AI 分析结果 + 画像摘要).

CREATE TABLE IF NOT EXISTS user_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_type TEXT NOT NULL,      -- interest | dislike | preference | summary
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    source TEXT NOT NULL,           -- ai_analysis | manual
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(memory_type, key)
);

CREATE INDEX IF NOT EXISTS idx_user_memory_type
    ON user_memory(memory_type);
