-- DEV-0182 hotfix (2026-09-12): 标讯数据最终清理 — 生产分库适配版
--
-- 首版在单库 (dev/test) 通过, 但生产是 HOT/WARM/COLD 三库 ATTACH:
-- content_fingerprints 实际在 warm 库, 其 FK 声明 REFERENCES hotspots
-- 按 SQLite 同库解析规则指向 warm.hotspots (不存在), FK ON 时对它的
-- DELETE 报 "no such table: warm.hotspots" → 迁移失败 → 启动失败。
-- 修复: 迁移首尾临时关闭/恢复 FK (PRAGMA 是连接级, 只影响本迁移执行)。
--
-- 表分布事实 (2026-09-12 生产只读核查):
--   main(hot): hotspots / favorites / favorites_snapshot / ai_scores /
--              hotspot_tags / bid_details / source_reputation
--   warm:      content_fingerprints
--
-- 保留: hotspots.bid_status / region 列 (死列, 代码 0 读写)。

PRAGMA foreign_keys = OFF;

DELETE FROM content_fingerprints
WHERE hotspot_id IN (SELECT id FROM hotspots WHERE category = 'bid');

DELETE FROM ai_scores
WHERE hotspot_id IN (SELECT id FROM hotspots WHERE category = 'bid');

DELETE FROM hotspot_tags
WHERE hotspot_id IN (SELECT id FROM hotspots WHERE category = 'bid');

DELETE FROM favorites
WHERE hotspot_id IN (SELECT id FROM hotspots WHERE category = 'bid');

DELETE FROM favorites_snapshot
WHERE hotspot_id IN (SELECT id FROM hotspots WHERE category = 'bid');

DELETE FROM hotspots WHERE category = 'bid';

DROP TABLE IF EXISTS bid_details;

DELETE FROM source_reputation WHERE source = 'bid_collector_default';

PRAGMA foreign_keys = ON;
