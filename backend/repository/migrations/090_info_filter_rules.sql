-- 090_info_filter_rules.sql
-- info_filter gate: 独立资讯筛选门禁规则表
--
-- 与 recency_gate / quality_gate 平行, 作用点不同:
-- - recency_gate / quality_gate: 单条 item 评估
-- - info_filter_gate: collector 启动前的源级白/黑名单
--
-- 4 种 match_kind 对应 4 种源识别粒度:
-- - category:       按 collector 分类 (ai / security / finance / tech / github / startup / ai_security)
-- - source_name:    按源名称 (微步在线 / 华尔街见闻 / InfoQ ...)
-- - source_id:      按 crawler_sources.id 精确匹配 (id = "category:source_name")
-- - tag:            按 item.tag 标签 (预留, 当前 item_builder 未打 tag, 字段可用)
--
-- rule_type allow/deny:
-- - deny: 优先级最高, 命中则拒绝 (用户显式黑名单)
-- - allow: 在 deny 之后评估, 命中则强制放行 (即使源被 global disabled)
--
-- 默认空表 (全 allow, 不限制). 启用与否走 feature_gate.info_filter 开关,
-- 不依赖表数据 — 关闭时 collector 完全不查表, 零开销。

CREATE TABLE IF NOT EXISTS info_filter_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_type TEXT NOT NULL CHECK (rule_type IN ('allow', 'deny')),
    match_kind TEXT NOT NULL CHECK (match_kind IN ('category', 'source_name', 'source_id', 'tag')),
    match_value TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_info_filter_enabled ON info_filter_rules(enabled);
CREATE INDEX IF NOT EXISTS idx_info_filter_match ON info_filter_rules(match_kind, match_value);
CREATE INDEX IF NOT EXISTS idx_info_filter_type_enabled ON info_filter_rules(rule_type, enabled);
