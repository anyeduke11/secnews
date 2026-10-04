-- 133_quality_custom_rules.sql — 质量自定义规则 (v0.8.6 P2, owner 裁决 2026-10-04)
-- 两层质量规则的自定义面: 专家规则 (确定性 matcher) + AI 语义规则 (NL 文本)。
-- 单表两用 (rule_kind 区分), 配置域 → main 库 (非流水, 不进 warm)。

CREATE TABLE IF NOT EXISTS quality_custom_rules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,                 -- 规则名 (UI 展示)
    rule_kind       TEXT NOT NULL DEFAULT 'expert',-- expert | semantic
    match_kind      TEXT NOT NULL,                 -- expert: title_contains|source_in|category_equals|url_matches|summary_len_lt ; semantic: nl
    match_value     TEXT NOT NULL,                 -- expert: 值(source_in 为 CSV) ; semantic: NL 规则文本
    action          TEXT NOT NULL DEFAULT 'flag',  -- expert: flag | reject (reject=hard 语义, strict 模式拒收); semantic 恒 flag
    deduction       INTEGER NOT NULL DEFAULT 10,   -- 命中扣分值 (0-100)
    scope_category  TEXT NOT NULL DEFAULT '',      -- 空 = 全部分类; 否则仅该分类
    enabled         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_qcr_kind_enabled ON quality_custom_rules(rule_kind, enabled);
