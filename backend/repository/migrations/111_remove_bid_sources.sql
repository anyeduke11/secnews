-- DEV-0178 (2026-09-12): 标讯采集链下线 — 工作台聚焦裁决 (owner, Workbench Focus PRD R2')
--
-- owner 追加裁决"剔除和安全从业者 AI 工作台中标讯相关的功能":
--   - bid_collector / parsers/bid (5 站) / bid_status / bid_alert API /
--     bid_detail_repo / bid_expiry_check job 代码已删除
--   - 本迁移清理 crawler_sources 中的 bid 源注册 (64 行), 使运行时源注册表
--     与代码一致, 避免 registry 引用已删除的 collector
--   - 保留: crawler_sources 其他列 / hotspots 表历史 bid 条目 / bid_details 表
--     (历史数据只读兼容, 前端已无 bid 入口)
--
-- 前置: 无 (幂等 DELETE)
-- 回滚: 无 (源定义可由 git 历史的 crawler_seed/seed 脚本重建)

DELETE FROM crawler_sources WHERE category = 'bid';
