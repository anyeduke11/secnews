-- 089_cleanup_null_url_sources.sql
-- P0 SSRF 副作用根除: 清空 crawler_sources 表里 29 行 url/feed_url/api_url 全空的源
-- (28 wechat 公众号 + 1 startup)。这些源不应进 registry 表 — 它们由主 collector
-- (SecurityCollector 等) 从类常量 SECURITY_SOURCES 加载, 不需要 url。
--
-- 历史: seed_crawler_sources.py 没像老脚本 crawler_seed.py:146 那样守 url,
-- 导致 wechat/sogou 源被错误注册。fetch_source 走 aiohttp fallback 时
-- session.get("") 抛 InvalidUrlClientError, 19+ 源永远 dead 状态污染指标。
--
-- 安全: 主 collector 仍能从 self.sources (类常量) 加载这些 wechat 源,
-- registry 表删除不影响主路径。本次只清状态 (无 schema 变更)。
--
-- Layer 1 of 4: 数据清理。

DELETE FROM crawler_sources
WHERE (url IS NULL OR url = '')
  AND (feed_url IS NULL OR feed_url = '')
  AND (api_url IS NULL OR api_url = '');
