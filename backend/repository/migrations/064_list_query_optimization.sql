-- 064_list_query_optimization.sql: v0.5 M1-Task1 主列表查询索引化
--
-- 背景: hotspot_repo.query() 主列表查询此前用 COALESCE(ingested_at,
-- published_at) 过滤/排序 + 4 个 quality_flags NOT LIKE 逐行计算,
-- EXPLAIN 显示 USE TEMP B-TREE FOR ORDER BY。配合离线回填
-- (backend/scripts/backfill_ingested_at.py, ingested_at 全量非 NULL +
-- is_hidden 推导), 查询层改为 ingested_at 直接比较 + is_hidden = 0,
-- 走本迁移创建的部分索引, 消除 TEMP B-TREE。
--
-- is_hidden: 由 quality_flags 推导的隐藏标记 (列表不展示):
--   historical_bid / historical_published / no_published_at /
--   landing_page_unresolvable 任一命中 → 1, 否则 0。
--   写入路径 (upsert_many / 修复脚本) 同步维护; 存量数据由离线脚本回填。
--
-- 幂等性: ALTER TABLE ADD COLUMN 在列已存在时抛 duplicate column,
-- 由 db.py 的 apply_migrations 容错; 索引用 IF NOT EXISTS。
-- 注意: 本迁移只含轻量 DDL, 禁止任何 UPDATE/数据回填
-- (启动时同步执行, 大表操作会卡死服务)。
ALTER TABLE hotspots ADD COLUMN is_hidden INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_list_visible
    ON hotspots(category, ingested_at DESC) WHERE is_hidden = 0;
