-- DEV-0187 (POST_R2 设计包 T2): hotspots 死列最终清理 — 标讯剔除收尾
--
-- 前置事实 (2026-09-12 生产只读核查):
--   SQLite ≥3.35 支持 DROP COLUMN (本仓 3.53.3)。
--   hotspots.region 被 idx_hotspot_region 索引引用 → 必须先 DROP INDEX。
--   hotspots.bid_status 无索引引用, 可直接 DROP。
--   weekly_reports.bid_summary 在 warm 库且有历史数据 → 保留不销毁。
-- 两列自 DEV-0180 起代码层 0 读写 (死列)。
--
-- 销毁型迁移: 不可回滚, 依赖备份链 (改库前已做 full backup + sha256 manifest)。

DROP INDEX IF EXISTS idx_hotspot_region;

ALTER TABLE hotspots DROP COLUMN region;

ALTER TABLE hotspots DROP COLUMN bid_status;
