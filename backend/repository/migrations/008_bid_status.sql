-- ============================================================================
-- 008_bid_status.sql — Phase 20 新增 bid_status 字段
--
-- 背景
-- ----
-- 标讯卡片需要显示"招标状态"标签(招标中/中标/变更/终止/成交),用户在前端
-- 看到列表时能区分:
--   - 招标公告 → 正在报名/投标
--   - 中标公告 → 已定标(看是否对应到我方)
--   - 变更公告 → 内容/时间有调整,需重新评估
--   - 终止公告 → 招标作废
--   - 成交公告 → 已完成交易
--
-- 提取由 :func:`backend.collectors.bid_status.extract_bid_status` 在
-- ingest 时通过正则从标题抽取,落库 bid_status 字段。
--
-- 幂等性
-- ------
-- 依赖 apply_migrations() 的 schema_version 记录,每个迁移只执行一次。
-- ============================================================================

ALTER TABLE hotspots ADD COLUMN bid_status TEXT;

CREATE INDEX IF NOT EXISTS idx_bid_status ON hotspots(category, bid_status)
WHERE category = 'bid';
