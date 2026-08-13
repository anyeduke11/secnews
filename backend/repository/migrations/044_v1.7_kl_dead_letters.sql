-- 044_v1.7_kl_dead_letters.sql
-- 目的: KL 触发器死信队列（重试 3 次失败后入队）
-- 来源: docs/hotspot_v1.7_PRD.md B.11.6 + .trae/specs/phase10-t1t2-triggers/spec.md §3.2

CREATE TABLE IF NOT EXISTS kl_dead_letters (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger_name  TEXT NOT NULL CHECK(trigger_name IN ('t1', 't2', 't3', 't4', 't5')),
    item_id       TEXT NOT NULL,                  -- knowledge_items.id
    error_msg     TEXT NOT NULL,                  -- 最后一次错误
    attempts      INTEGER NOT NULL DEFAULT 0,     -- 累计尝试次数
    payload       TEXT,                           -- JSON 序列化上下文
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    last_retry_at TEXT,
    resolved      INTEGER NOT NULL DEFAULT 0 CHECK(resolved IN (0, 1))
);
CREATE INDEX IF NOT EXISTS idx_dl_trigger_resolved ON kl_dead_letters(trigger_name, resolved);
CREATE INDEX IF NOT EXISTS idx_dl_item_id ON kl_dead_letters(item_id);
