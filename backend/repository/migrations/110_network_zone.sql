-- 110_network_zone.sql
-- 代理内置批 T6: 显式建立信源的国际/国内归属 (network_zone), 作为抓取网络路径的单一事实源。
--
-- 背景: 代理是兜底 (直连优先), 但国外源 (github.com / thehackernews.com 等) 直连 15s 黑洞,
-- 每轮先烧一次直连超时才轮到代理。owner 裁决: 国外源直接用代理 (代理优先, 失败仍回直连)。
-- prefer_proxy() 读本列判定 (仅 enabled=1 生效); 国内源命中 no_proxy 永远直连。
--
-- 归属判定 (2026-09-10 人工核定, 依据 audit_dead_source_triage + /api/proxy/test A/B 实测):
--   international: github.com, news.ycombinator.com, hnrss.org, thehackernews.com,
--                  hackread.com, schneier.com
--   domestic:      其余全部 (含 Cloudflare 托管的 4hou.com —— 直连实测正常, 内容为国内媒体)
-- 新增国外源时 INSERT 后手工 UPDATE network_zone='international' (或经设置页调整)。

ALTER TABLE crawler_sources ADD COLUMN network_zone TEXT NOT NULL DEFAULT 'domestic';

UPDATE crawler_sources
SET network_zone = 'international',
    updated_at = datetime('now')
WHERE url LIKE '%://github.com/%'
   OR url LIKE '%://news.ycombinator.com%'
   OR url LIKE '%://hnrss.org/%'
   OR url LIKE '%://thehackernews.com%'
   OR url LIKE '%://hackread.com%'
   OR url LIKE '%://schneier.com%'
   OR feed_url LIKE '%://github.com/%'
   OR feed_url LIKE '%://news.ycombinator.com%'
   OR feed_url LIKE '%://hnrss.org/%'
   OR feed_url LIKE '%://thehackernews.com%'
   OR feed_url LIKE '%://hackread.com%'
   OR feed_url LIKE '%://schneier.com%';
