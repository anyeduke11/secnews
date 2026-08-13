-- 058_v1.7_recreate_knowledge_tasks.sql
-- Cubox sync 需要 knowledge_tasks 表跟踪异步任务进度。
-- 该表在 038_v1.7_drop_phase5_tables.sql 中被删除（Phase 5 cleanup），
-- 但 Cubox sync 功能（Phase 8+）依赖它。此处重新创建。
-- 参考: 018_knowledge.sql 中的原始定义

CREATE TABLE IF NOT EXISTS knowledge_tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type       TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    params          TEXT DEFAULT '{}',
    result_path     TEXT DEFAULT '',
    error_message   TEXT DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);