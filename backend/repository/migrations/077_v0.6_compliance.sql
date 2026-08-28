-- S4-4: 合规矩阵数据表 (等保 2.0 + GDPR + ISO 27001)
-- ============================================================================
-- compliance_controls    — 合规控制项静态表 (framework, control_id 联合主键)
-- compliance_event_map   — 事件类型 → 合规条款映射表
--
-- 幂等: IF NOT EXISTS + 唯一约束保证重复执行安全
-- ============================================================================

CREATE TABLE IF NOT EXISTS compliance_controls (
    framework    TEXT    NOT NULL,
    control_id   TEXT    NOT NULL,
    name         TEXT    NOT NULL DEFAULT '',
    description  TEXT    NOT NULL DEFAULT '',
    PRIMARY KEY (framework, control_id)
);

CREATE INDEX IF NOT EXISTS idx_compliance_controls_framework
    ON compliance_controls(framework);

CREATE TABLE IF NOT EXISTS compliance_event_map (
    event_type   TEXT    NOT NULL,
    framework    TEXT    NOT NULL,
    control_id   TEXT    NOT NULL,
    PRIMARY KEY (event_type, framework, control_id)
);

CREATE INDEX IF NOT EXISTS idx_compliance_event_map_event
    ON compliance_event_map(event_type);
