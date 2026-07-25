-- Migration 041: 扩展 collection_runs.status CHECK 约束,允许 'running'.
--
-- Phase 8 背景: catchup_watchdog_job 需要检测 started_at > 10min 未 finished
-- 的孤儿行. 但当前 schema 的 status CHECK 只允许 (success/partial/failed),
-- 所以 collection_service 只能在采集结束时写一行, 中间状态没有持久化.
--
-- 修复: 扩展 CHECK 增加 'running' 状态, collection_service 在每个 category
-- collector 开始时立即 INSERT 一行 running 状态, 结束时再 UPDATE 同一行.
-- watchdog 通过 `WHERE status='running' AND started_at < now-600s` 检测孤儿.
--
-- 兼容性: 原值 (success/partial/failed) 保留, 不影响历史数据.
-- 索引: idx_runs_started 已覆盖 started_at 查询.

-- SQLite 不支持 ALTER CHECK, 必须重建表.
-- 步骤: create new -> copy data -> drop old -> rename new

CREATE TABLE IF NOT EXISTS collection_runs_new (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    category        TEXT    NOT NULL,
    started_at      TEXT    NOT NULL,
    finished_at     TEXT,
    status          TEXT    NOT NULL CHECK (status IN ('success','partial','failed','running')),
    item_count      INTEGER NOT NULL DEFAULT 0,
    fallback_count  INTEGER NOT NULL DEFAULT 0,
    error_msg       TEXT
);

INSERT INTO collection_runs_new
    (id, category, started_at, finished_at, status, item_count, fallback_count, error_msg)
SELECT id, category, started_at, finished_at, status, item_count, fallback_count, error_msg
FROM collection_runs;

DROP TABLE collection_runs;

ALTER TABLE collection_runs_new RENAME TO collection_runs;

CREATE INDEX IF NOT EXISTS idx_runs_started  ON collection_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_category ON collection_runs(category, started_at DESC);
-- Phase 8: watchdog 查询 `status='running' AND started_at < cutoff` 用
CREATE INDEX IF NOT EXISTS idx_runs_status_started ON collection_runs(status, started_at DESC);
