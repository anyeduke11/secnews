-- 121_source_media_kind.sql: 数据源治理 T1 — 介质维度 + 搜狗归档 + 多媒体首批源
-- (docs/superpowers/specs/2026-09-26-source-governance-design.md §3.1/§3.4)
--
-- media_kind = 「介质」维度 (web/wechat/multimedia), 与 kind (采集方式
-- html/rss) 正交; 前端源矩阵按它分组。crawler_sources 顺带补 notes 列
-- (多媒体源 probe 结论的落库载体, 语义自由文本)。
--
-- 归档语义 (owner 裁决 §2): 微信通道归档待替代 — crawler_sources 注册层
-- 搜狗行 retired+enabled=0 (幂等防御, 实测 2026-09-26 当前 0 行);
-- source_stats 统计层搜狗行只标 media_kind, 不删不 retire (有历史产出,
-- 属可复活候选, T2 清理脚本管辖范围外)。
-- source_alerts 告警 NOT EXISTS 防重: 通道级事实不依赖注册层是否有行。
--
-- ALTER TABLE 非 idempotent, 但 schema_version 保证单库只执行一次
-- (migration 119/120 同款先例)。

ALTER TABLE crawler_sources ADD COLUMN media_kind TEXT NOT NULL DEFAULT 'web';
ALTER TABLE source_stats ADD COLUMN media_kind TEXT NOT NULL DEFAULT 'web';
ALTER TABLE crawler_sources ADD COLUMN notes TEXT;

-- 存量回填推断: name 含 (搜狗) → wechat; url/name 含 youtube/bilibili →
-- multimedia; 其余保持缺省 web。
UPDATE crawler_sources SET media_kind = 'wechat'
WHERE name LIKE '%(搜狗)%';

UPDATE source_stats SET media_kind = 'wechat'
WHERE source_name LIKE '%(搜狗)%';

UPDATE crawler_sources SET media_kind = 'multimedia'
WHERE url LIKE '%youtube.com/%' OR url LIKE '%bilibili%'
   OR feed_url LIKE '%youtube.com/%' OR feed_url LIKE '%bilibili%';

UPDATE source_stats SET media_kind = 'multimedia'
WHERE source_url LIKE '%youtube.com/%' OR source_url LIKE '%bilibili%'
   OR source_name LIKE '%youtube%' OR source_name LIKE '%bilibili%';

-- 搜狗归档 (注册层, 幂等: 已 retired+disabled 不重复触碰) + 通道级 P2 告警。
UPDATE crawler_sources
SET status = 'retired',
    enabled = 0,
    updated_at = datetime('now')
WHERE name LIKE '%(搜狗)%'
  AND (status != 'retired' OR enabled != 0);

INSERT INTO source_alerts (source_id, alert_type, level, message, detail, created_at)
SELECT 'security:搜狗(微信镜像)',
       'source_archived_wechat',
       'P2',
       '微信通道(搜狗镜像)已归档待替代: 2026-08 起被搜狗反爬封禁, '
       || '相关源标 media_kind=wechat 保留审计, 待 RSSHub 等自建替代通道后复活',
       '{"media_kind":"wechat","reason":"sogou_mirror_blocked","stats_layer":"kept_as_revival_candidate"}',
       datetime('now')
WHERE NOT EXISTS (
    SELECT 1 FROM source_alerts WHERE alert_type = 'source_archived_wechat'
);

-- 多媒体首批源 (§3.4): YouTube 安全频道公开 RSS ×2。
-- probe 2026-09-26 直连失败 (proxy_config.json 未配代理, Connection reset)
-- → enabled=0 + status='disabled' 落库, notes 指引 owner 配置代理后激活;
-- YouTube 属国际源: use_proxy='required' + network_zone='international'
-- (migration 110 判定惯例)。
INSERT OR IGNORE INTO crawler_sources
    (id, category, name, kind, url, feed_url,
     cadence_seconds, priority, max_items,
     enabled, use_proxy, status, media_kind, network_zone, notes)
VALUES
    ('security:LiveOverflow (YouTube)', 'security', 'LiveOverflow (YouTube)', 'rss',
     'https://www.youtube.com/feeds/videos.xml?channel_id=UCu6mSoMNzHQiBIOkAgf7A9g',
     'https://www.youtube.com/feeds/videos.xml?channel_id=UCu6mSoMNzHQiBIOkAgf7A9g',
     3600, 45, 30,
     0, 'required', 'disabled', 'multimedia', 'international',
     '待 owner 配置代理后启用 (probe 2026-09-26 直连 Connection reset; channel UCu6mSoMNzHQiBIOkAgf7A9g 公开可查)'),
    ('security:John Hammond (YouTube)', 'security', 'John Hammond (YouTube)', 'rss',
     'https://www.youtube.com/feeds/videos.xml?channel_id=UCVeW9qkBjo3zosnqUbG7FPw',
     'https://www.youtube.com/feeds/videos.xml?channel_id=UCVeW9qkBjo3zosnqUbG7FPw',
     3600, 45, 30,
     0, 'required', 'disabled', 'multimedia', 'international',
     '待 owner 配置代理后启用 (probe 2026-09-26 直连 Connection reset; channel UCVeW9qkBjo3zosnqUbG7FPw 公开可查)');
