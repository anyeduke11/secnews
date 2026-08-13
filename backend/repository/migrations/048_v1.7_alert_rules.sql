-- ============================================================================
-- 048_v1.7_alert_rules.sql — Phase 12 告警规则定义与告警事件表
--
-- 背景
-- ----
-- Phase 12 引入新的告警系统, 替代 Phase 3 (028_v1.7_alert_rules.sql)
-- 的旧 alert_rules 表。新系统使用 alert_rule_definitions 和 alert_events
-- 表名, 避免与旧表冲突。
--
-- 规则类型
-- --------
-- - tech_stack_cve: 新 CVE 命中 cg_projects.tech_stack 时触发
-- - critical_cve:   NVD CVSS ≥ 9.0 的 CVE 触发
-- - bid_match:      标讯关键词命中 tech_stack 时触发
--
-- 幂等性
-- ----
-- CREATE TABLE IF NOT EXISTS 确保幂等,
-- apply_migrations() 记录 schema_version 防止重复执行。
-- ============================================================================

-- 1. 告警规则定义表
CREATE TABLE IF NOT EXISTS alert_rule_definitions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT,
    rule_type   TEXT NOT NULL CHECK(rule_type IN ('tech_stack_cve', 'critical_cve', 'bid_match')),
    enabled     INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
    config      TEXT,  -- JSON config (e.g., window_hours, min_cvss)
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_alert_rule_definitions_type ON alert_rule_definitions(rule_type);

-- 2. 告警事件表
CREATE TABLE IF NOT EXISTS alert_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id     INTEGER REFERENCES alert_rule_definitions(id),
    rule_type   TEXT NOT NULL,
    title       TEXT NOT NULL,
    description TEXT,
    severity    TEXT NOT NULL CHECK(severity IN ('critical', 'high', 'medium', 'low')),
    source      TEXT,  -- trigger source (e.g., CVE ID, bid title)
    source_url  TEXT,
    item_id     TEXT,  -- related knowledge item ID
    project_id  INTEGER,  -- related cg_projects ID
    status      TEXT NOT NULL DEFAULT 'unread' CHECK(status IN ('unread', 'read', 'resolved')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    read_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_alert_events_status ON alert_events(status);
CREATE INDEX IF NOT EXISTS idx_alert_events_created ON alert_events(created_at);
CREATE INDEX IF NOT EXISTS idx_alert_events_rule_type ON alert_events(rule_type);

-- 3. 种子数据：3 条默认规则
INSERT INTO alert_rule_definitions (name, description, rule_type, config) VALUES
('技术栈 CVE 影响', '新 CVE 命中 cg_projects.tech_stack 时触发', 'tech_stack_cve', '{"window_hours": 24}'),
('关键 CVE 告警', 'NVD CVSS ≥ 9.0 的 CVE 触发', 'critical_cve', '{"min_cvss": 9.0}'),
('标讯技术栈匹配', '标讯关键词命中 tech_stack 时触发', 'bid_match', '{"window_hours": 24}');