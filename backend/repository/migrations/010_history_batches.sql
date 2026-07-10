-- ============================================================================
-- 010_history_batches.sql — Phase 28 历史资讯: favorites_snapshot schema 预留
--
-- 背景
-- ----
-- 用户需求: "每隔7天前端更新一批, 但是后台都会存储起来"
--   - 资讯和标讯按 7 天自然周边界分批, 前端可下钻任意历史批次阅读/筛选/收藏
--   - 后台不删 hotspots(永久保留)
--   - 收藏的 item 走 favorites 表(已有), 不需要 snapshot
--
-- 预留 favorites_snapshot 表
-- --------------------------
-- 现阶段不实现 hard delete, 该表只保留 schema 供未来:
--   1. 当 hotspots 表需要清理 (如 > 26 周 + 未收藏) 时, 把被收藏的拷贝进来
--   2. 当 hotspots 被 hard delete 后, 收藏仍能通过 snapshot 展示完整内容
-- 现阶段不写入数据, 不实现迁移逻辑 (YAGNI).
--
-- 字段与 favorites 表同构, 但 hotspot_id 不带 UNIQUE 约束 (允许同 hotspot
-- 多次 snapshot, 用于记录收藏时间点)
-- ============================================================================

CREATE TABLE IF NOT EXISTS favorites_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hotspot_id TEXT NOT NULL,                 -- 逻辑外键 → hotspots.id
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    favorited_at TEXT NOT NULL,               -- 收藏时间
    snapshotted_at TEXT NOT NULL,             -- snapshot 时间 (被 hard delete 时填)
    batch_no INTEGER NOT NULL                 -- snapshot 时的批次号
);

CREATE INDEX IF NOT EXISTS idx_fav_snap_hotspot
    ON favorites_snapshot(hotspot_id);

CREATE INDEX IF NOT EXISTS idx_fav_snap_batch
    ON favorites_snapshot(batch_no);

CREATE INDEX IF NOT EXISTS idx_fav_snap_snapshotted_at
    ON favorites_snapshot(snapshotted_at DESC);
