-- 109_cadence_seconds_rebase.sql
-- cadence 修正批: crawler_sources.cadence_seconds 从统一 300 重基到 per-source 差异节奏。
--
-- 背景: 055 建表时该列默认 300, seed 全部写 300, 但 get_schedulable / 批量 collect
-- 从未读它 (死列) — 87 个启用源 (含 62 个政企招标站) 被统一按 5 分钟全量轮询,
-- 7 天 3 万次 run 里 failed+partial 占 2 万。本批把列接线为单一闸口
-- (BaseCollector._load_sources_from_registry + SourceSchedulerRepository.get_schedulable),
-- 这里只重基数据:
--   * 全部启用源 → 1800 (30 分钟, 与 config.collect_interval_seconds 新默认一致)
--   * bid 类 → 21600 (6 小时: 招标公告本身日更级, 且这类站 DNS/SSL/WAF 敌对性最强,
--     高频只会加速封禁; 存活的 2 个 bid 源 3 天内才有一次成功, 6h 足够)
-- 只动 cadence_seconds, 不动 status/enabled (退役由 cleanup_retire_unfixable_sources.py
-- 按诊断结论单独处理)。幂等: 重跑结果相同。

UPDATE crawler_sources
SET cadence_seconds = 1800,
    updated_at = datetime('now')
WHERE enabled = 1;

UPDATE crawler_sources
SET cadence_seconds = 21600,
    updated_at = datetime('now')
WHERE enabled = 1
  AND category = 'bid';
