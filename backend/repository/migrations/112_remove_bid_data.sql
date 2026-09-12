-- DEV-0180 (2026-09-12): 标讯数据最终清理 — 工作台聚焦裁决 (owner: "不需要有意保留, 直接清理")
--
-- 前置: 111_remove_bid_sources.sql (源注册清理)。本迁移收尾数据层:
--   1. 删除全部 category='bid' 的 hotspots 行及其子表数据
--      (content_fingerprints / ai_scores / hotspot_tags 有 ON DELETE CASCADE;
--       favorites / favorites_snapshot 为逻辑外键, 需显式删除)
--   2. DROP bid_details 表 (055 建立的结构化标讯表, 采集器已删, 数据作废)
--   3. 清理 source_reputation 的 bid_collector_default 种子行 (002 历史种子)
--
-- 保留: hotspots.bid_status / hotspots.region 列 (SQLite DROP COLUMN 受索引
--       约束风险高, 列已为死列 — 代码层 0 读写); todos.source_id 悬空链接
--       (011 设计: todo 带快照字段, hotspot 删除后 todo 仍完整)。
-- 前置: 无。回滚: 无 (数据销毁性, 属 owner 裁决的剔除范围)。

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
