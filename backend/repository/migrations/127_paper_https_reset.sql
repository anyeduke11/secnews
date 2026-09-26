-- 127_paper_https_reset.sql: 论文源 HTTPS 化 + 健康状态重置 (2026-09-27)
--
-- 根因 (合并后真实回归, 实测取证): 123 种子用 http://export.arxiv.org
-- → arXiv 301→https 多一跳; 更致命的是 source_prober.probe_all_dead
-- 对 14 条 dead 源零节拍连发 HEAD, 违反 arXiv "单请求 ≥3s" 官方约束
-- → Fastly 间歇性拒绝 (400/406, 同一 URL 实测 200/406 随机), 14 源
-- unknown→stale(3)→dead(5) 五连败, T1 永不抓 dead 源, paper 能力
-- 从未生效 (hotspots paper 条目 = 0)。
--
-- 修复: ① 28 条 URL 升 https (少一跳重定向) ② 重置健康状态回
-- unknown 冷启动漏斗 (从未成功过, 语义最正)。
-- 探测端配套: probe_all_dead 同 host 3.1s 节拍 (同 commit)。
-- 123/125 在本机已应用, 按 append-only 纪律追加本迁移;
-- 新库 123 → 125 → 127 顺序执行, replace 无命中时为幂等 no-op。

UPDATE crawler_sources
SET feed_url    = replace(feed_url, 'http://export.arxiv.org', 'https://export.arxiv.org'),
    api_url     = replace(api_url,  'http://export.arxiv.org', 'https://export.arxiv.org'),
    status               = 'unknown',
    consecutive_failures = 0,
    grace_rounds         = 0,
    last_error           = NULL,
    cooldown_until       = NULL,
    last_fetch_at        = NULL,
    updated_at           = datetime('now')
WHERE category = 'paper';
