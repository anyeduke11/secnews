-- ============================================================================
-- 062_quality_logs_archive.sql — P0.1 quality_check_logs 归档表
--
-- 背景:
--   quality_check_logs 是 DB 膨胀主因 (440 万行 / 1.35GB, 见 scheduler.py 注释)。
--   原 cleanup 直接 DELETE, 但 SQLite DELETE 后空间不自动回收 (除非 VACUUM)。
--
-- 方案:
--   创建归档表 quality_check_logs_archive (与主表同结构, 无索引, 节省空间)。
--   cleanup 流程改为:
--     1. INSERT INTO archive SELECT 超过保留窗口的行
--     2. DELETE FROM main WHERE 超过保留窗口
--     3. PRAGMA incremental_vacuum 回收主表空间
--
--   归档表保留 90 天 (调试追溯用), 超过 90 天的归档行由独立 job 清理。
--
-- 保留窗口:
--   主表: 7 天 (原 30 天; summary_24h 只看最近 24h, 7 天足够调试)
--   归档表: 90 天
-- ============================================================================

CREATE TABLE IF NOT EXISTS quality_check_logs_archive (
    id              INTEGER PRIMARY KEY,    -- 保留原 id (不 AUTOINCREMENT)
    item_id         TEXT NOT NULL,
    gate_name       TEXT NOT NULL,
    passed          INTEGER NOT NULL,
    score_deduction INTEGER NOT NULL DEFAULT 0,
    flags           TEXT NOT NULL DEFAULT '[]',
    reason          TEXT,
    error_msg       TEXT,
    checked_at      TEXT NOT NULL,
    mode            TEXT NOT NULL DEFAULT 'loose',
    archived_at     TEXT NOT NULL            -- 归档时间, ISO 8601 UTC
);

-- 归档表只建一个索引 (按时间查), 不建其他索引以节省空间
CREATE INDEX IF NOT EXISTS idx_qcl_archive_time ON quality_check_logs_archive(checked_at DESC);
