-- 125_paper_sortby_fix.sql: DEV-0233 Task 2 真实拉取验证修复
--
-- migration 123 种子的 28 条 URL (feed_url/api_url) 误写 sortBy=submitted
-- — arXiv API 合法值为 relevance / lastUpdatedDate / submittedDate。
-- 误值不报错, 而是返回仅含 1 条 Error entry 的 Atom feed, 3 领域轮转
-- 恰凑满 min_items_threshold=3, 垃圾条目会静默入 feed。
--
-- 123 在本机已应用 (schema_version 无内容校验, 改文件不重跑),
-- 故按 append-only 纪律追加本迁移对已注册行做字符串替换;
-- 新库 123 → 125 顺序执行, replace 无命中时为幂等 no-op。
-- 采集器类常量 (arxiv_paper_collector._ARXIV_API) 已同 commit 修正。

UPDATE crawler_sources
SET feed_url = replace(feed_url, 'sortBy=submitted&', 'sortBy=submittedDate&'),
    api_url  = replace(api_url,  'sortBy=submitted&', 'sortBy=submittedDate&')
WHERE category = 'paper'
  AND feed_url LIKE '%sortBy=submitted&%';
