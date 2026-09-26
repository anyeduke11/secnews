-- 122_source_cleanup_log.sql: 数据源治理 T2 — 源清理审计表
-- (docs/superpowers/specs/2026-09-26-source-governance-design.md §3.2/§3.3)
--
-- 任何源删除/启停动作必须先写本表再动数据 (审计强制):
-- - source_layer: 数据所在层 ('crawler_sources' 注册层 / 'source_stats' 统计层)
-- - source_ident: 行标识 (crawler_sources.name / source_stats.source_name 或 url)
-- - reason: 清理原因 (脚本 'never_yielded_dead_cleanup' / API owner 传入)
-- - executed_by: 'system' (脚本) / 'owner' (API 手动操作)
--
-- CREATE TABLE IF NOT EXISTS: 本表无 ALTER, 天然幂等。

CREATE TABLE IF NOT EXISTS source_cleanup_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_layer TEXT NOT NULL,
    source_ident TEXT NOT NULL,
    reason TEXT NOT NULL,
    executed_at TEXT NOT NULL DEFAULT (datetime('now')),
    executed_by TEXT NOT NULL DEFAULT 'system'
);

CREATE INDEX IF NOT EXISTS idx_source_cleanup_log_ident
    ON source_cleanup_log (source_layer, source_ident);
