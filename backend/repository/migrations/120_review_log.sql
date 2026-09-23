-- 120_review_log.sql: 复习栈能力丰富 (2026-09-21 设计稿 §3.1)
-- review_log = 撤销与统计的唯一真数据源; 每次评分写一条 旧→新 全量快照
-- (含 prev_last_grade/prev_last_reviewed_at, undo 逐级回退需要)。
-- sm2_reviews 加 suspended 列 (暂停卡不进 due 队列与预报)。
--
-- 表温度归属以 scripts/retention.json 为权威 (DEV-0226 教训):
-- sm2_reviews 已登记 temp=HOT; review_log 同温度落 main, retention.json 随行补条目。
--
-- ALTER TABLE 非 idempotent, 但 schema_version 保证单库只执行一次
-- (migration 119 同款先例)。

CREATE TABLE IF NOT EXISTS review_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    grade INTEGER NOT NULL,
    prev_easiness REAL, prev_interval INTEGER, prev_repetitions INTEGER,
    prev_due_at TEXT, prev_last_reviewed_at TEXT, prev_last_grade INTEGER,
    new_easiness REAL NOT NULL, new_interval INTEGER NOT NULL,
    new_repetitions INTEGER NOT NULL, new_due_at TEXT NOT NULL,
    reverted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rlog_entity ON review_log(entity_type, entity_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_rlog_created ON review_log(created_at DESC);
ALTER TABLE sm2_reviews ADD COLUMN suspended INTEGER NOT NULL DEFAULT 0;
