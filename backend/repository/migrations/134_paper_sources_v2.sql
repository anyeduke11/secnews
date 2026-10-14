-- 134_paper_sources_v2.sql: 论文多源扩展 — 5 个公开高质量 AI / 网络信息安全论文源
--
-- 背景: migration 123 只注册了 arXiv 14 领域源; 本迁移追加 5 个国际公开学术源
-- (OpenAlex / Semantic Scholar / IACR ePrint / Crossref / Hugging Face Daily
-- Papers), 与既有 ArxivPaperCollector 同属 category='paper', 由
-- backend/collectors/paper_sources.py 的 5 个 collector 承接。
--
-- 与 "crawler_sources 切流" 机制对齐 (collectors/base.py:_load_sources_from_registry):
-- 注册行 name 必须与 collector 类常量 sources[].name 逐字一致, 否则源归属隔离
-- (PaperProviderMixin._load_sources_from_registry 按自身源名过滤) 会丢弃该行。
--
-- feed_url/api_url 语义 (fetchers.py:fetch_source 路由):
-- - JSON 源 (kind='json'): 端点填 api_url, feed_url 留 NULL。
--   fetch_source 判定 `if source.get("rss_url")` 优先 — feed_url 非空会误走
--   _fetch_rss/feedparser 路径; JSON 源必须 feed_url 为空。
-- - RSS 源 (kind='rss'): 端点填 feed_url (registry 装载映射为 rss_url),
--   api_url 留 NULL。
--
-- 动态日期窗: OpenAlex / Semantic Scholar / Crossref 端点保留
-- {from_date} / {to_date} 占位, 抓取前由 PaperProviderMixin.fetch_source 注入
-- 最近 21 天实时窗口 (避免拉回未来日期或陈年论文); 落库端再由 item_builder
-- 的 14 天论文窗口收口。
--
-- 国际源: use_proxy='auto' + network_zone='international' (migration 110/121
-- 判定惯例; JSON 首跳直连, 失败后 _proxy_json_retry 按 should_use_proxy 代理
-- 兜底; RSS 经 ProxySession 代理感知)。status='unknown' 走健康机冷启动探活漏斗。
--
-- cadence=3600: 论文日更节奏远慢于新闻; priority=45 辅助档 (123/121 同档)。
-- INSERT OR IGNORE: 幂等 (123 同款写法)。本迁移晚于 125/127, 其
-- `WHERE category='paper'` 的 UPDATE 不会触及本批新行。

INSERT OR IGNORE INTO crawler_sources
    (id, category, name, kind, url, feed_url, api_url,
     cadence_seconds, priority, max_items,
     enabled, use_proxy, status, media_kind, network_zone, notes)
VALUES
    ('paper:openalex', 'paper', 'OpenAlex', 'json',
     'https://openalex.org/',
     NULL,
     'https://api.openalex.org/works?filter=type:article,primary_topic.field.id:fields/17,from_publication_date:{from_date},to_publication_date:{to_date}&sort=publication_date:desc&per-page=25',
     3600, 45, 20, 1, 'auto', 'unknown', 'web', 'international',
     '国际源需代理; OpenAlex works API (CS 领域); 动态日期窗'),
    ('paper:semantic_scholar', 'paper', 'Semantic Scholar', 'json',
     'https://www.semanticscholar.org/',
     NULL,
     'https://api.semanticscholar.org/graph/v1/paper/search/bulk?query=security&fields=title,url,publicationDate,externalIds&fieldsOfStudy=Computer%20Science&publicationDateOrYear={from_date}:{to_date}&sort=publicationDate:desc',
     3600, 45, 20, 1, 'auto', 'unknown', 'web', 'international',
     '国际源需代理; Semantic Scholar bulk search; 限流敏感'),
    ('paper:iacr_eprint', 'paper', 'IACR ePrint', 'rss',
     'https://eprint.iacr.org/',
     'https://eprint.iacr.org/rss/rss.xml',
     NULL,
     3600, 45, 20, 1, 'auto', 'unknown', 'web', 'international',
     '国际源需代理; IACR Cryptology ePrint Archive (RSS, 密码学专门源)'),
    ('paper:crossref', 'paper', 'Crossref', 'json',
     'https://www.crossref.org/',
     NULL,
     'https://api.crossref.org/works?filter=from-pub-date:{from_date},until-pub-date:{to_date},type:journal-article&query=security&rows=20&sort=published&order=desc&select=DOI,title,published,published-online,URL,container-title,type',
     3600, 45, 20, 1, 'auto', 'unknown', 'web', 'international',
     '国际源需代理; Crossref works API (期刊论文); 动态日期窗'),
    ('paper:hf_daily_papers', 'paper', 'Hugging Face Daily Papers', 'json',
     'https://huggingface.co/papers',
     NULL,
     'https://huggingface.co/api/daily_papers',
     3600, 45, 20, 1, 'auto', 'unknown', 'web', 'international',
     '国际源需代理; HF Daily Papers (通用 AI/ML 为主)');