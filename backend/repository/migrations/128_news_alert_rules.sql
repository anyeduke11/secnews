-- 128_news_alert_rules.sql
-- 2026-09-27 四模式重定义 P1 (spec §2): 资讯告警 4 规则定义。
-- alert_events 零 DDL (13 列够用); 规则 INSERT 幂等 (NOT EXISTS)。
--
-- ⚠ 实施修正 (vs 计划原文): 048_v1.7_alert_rules.sql 对 rule_type 加了
-- CHECK(rule_type IN ('tech_stack_cve','critical_cve','bid_match')),
-- 4 个新 rule_type 直接 INSERT 会 CHECK constraint failed。故先按 SQLite
-- 官方 altertable 重建流程扩 CHECK (3 旧 + 4 新 = 7 值); alert_events.rule_id
-- REFERENCES 本表, 按 126_foreign_keys_off_note.sql 规约 FK OFF/ON 成对包裹
-- (先例 112_remove_bid_data.sql), 阻断 DROP 被引用父表时级联扩散。

PRAGMA foreign_keys = OFF;

-- 1. 扩 rule_type CHECK: 建 → 拷 → 删旧 → 改名 (009/041/047 同款)
DROP TABLE IF EXISTS alert_rule_definitions_new;  -- 半途失败残骸清理
CREATE TABLE alert_rule_definitions_new (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT,
    rule_type   TEXT NOT NULL CHECK(rule_type IN (
        'tech_stack_cve', 'critical_cve', 'bid_match',
        'critical_vuln', 'major_security_event',
        'major_ai_security_event', 'must_know_regulatory')),
    enabled     INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
    config      TEXT,  -- JSON config (e.g., window_hours, min_cvss)
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT
);
INSERT INTO alert_rule_definitions_new (
    id, name, description, rule_type, enabled, config, created_at, updated_at)
SELECT id, name, description, rule_type, enabled, config, created_at, updated_at
FROM alert_rule_definitions;
DROP TABLE alert_rule_definitions;
ALTER TABLE alert_rule_definitions_new RENAME TO alert_rule_definitions;
CREATE INDEX IF NOT EXISTS idx_alert_rule_definitions_type
    ON alert_rule_definitions(rule_type);

PRAGMA foreign_keys = ON;

-- 2. 资讯告警 4 规则定义 (幂等 NOT EXISTS)
INSERT INTO alert_rule_definitions (name, rule_type, enabled, config, created_at, updated_at)
SELECT '需打补丁/排查的漏洞', 'critical_vuln', 1,
       '{"max_per_run": 5, "keywords": ["在野利用", "exploited in the wild", "0day", "零日", "PoC", "概念验证", "紧急补丁", "out-of-band"]}',
       datetime('now'), datetime('now')
WHERE NOT EXISTS (SELECT 1 FROM alert_rule_definitions WHERE rule_type = 'critical_vuln');

INSERT INTO alert_rule_definitions (name, rule_type, enabled, config, created_at, updated_at)
SELECT '需资产排查/响应的安全事件', 'major_security_event', 1,
       '{"max_per_run": 5, "keywords": ["遭攻击", "hacked", "breach", "数据泄露", "勒索攻击", "供应链攻击", "关基", "critical infrastructure", "APT", "失陷"], "min_signals_alone": 2, "quality_score_gate": 75}',
       datetime('now'), datetime('now')
WHERE NOT EXISTS (SELECT 1 FROM alert_rule_definitions WHERE rule_type = 'major_security_event');

INSERT INTO alert_rule_definitions (name, rule_type, enabled, config, created_at, updated_at)
SELECT 'AI 资产需行动的事件', 'major_ai_security_event', 1,
       '{"max_per_run": 5, "keywords": ["AI黑客", "AI 黑客", "deepfake", "深度伪造", "提示注入", "prompt injection", "模型投毒", "AI 漏洞", "LLM 漏洞", "MCP 漏洞"], "ai_context_words": ["AI", "LLM", "大模型", "GPT", "Claude", "agent", "智能体"]}',
       datetime('now'), datetime('now')
WHERE NOT EXISTS (SELECT 1 FROM alert_rule_definitions WHERE rule_type = 'major_ai_security_event');

INSERT INTO alert_rule_definitions (name, rule_type, enabled, config, created_at, updated_at)
SELECT '监管/政策限时执行', 'must_know_regulatory', 1,
       '{"max_per_run": 5, "keywords": ["紧急通报", "公安部", "报送", "等保", "CISA", "advisory"]}',
       datetime('now'), datetime('now')
WHERE NOT EXISTS (SELECT 1 FROM alert_rule_definitions WHERE rule_type = 'must_know_regulatory');
