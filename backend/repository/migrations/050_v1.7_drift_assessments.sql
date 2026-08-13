-- migration 050_v1.7_drift_assessments.sql
-- 目的: Phase 14 子系统联动 — tech_stack_drift 评估记录表
--
-- 设计决策
-- --------
-- - cg_drift_assessments 表: 记录 Knowledge → Codegarden 技术栈漂移评估
-- - UNIQUE(project_id, tech_name) 防止同一项目同 tech 重复评估
-- - status CHECK 约束: pending / reviewed / applied / dismissed
-- - security_entities.entity_type 校验在应用层验证 (SQLite 不支持
--   ALTER TABLE ADD CHECK, 不修改已有 migration 022)
--
-- 参考
-- ----
-- - spec: .trae/specs/phase14-subsystem-linkage/spec.md §3.1

CREATE TABLE IF NOT EXISTS cg_drift_assessments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      TEXT NOT NULL,               -- cg_projects.id
    tech_name       TEXT NOT NULL,               -- 发现的新技术栈名称
    source_item_id  TEXT,                        -- 来源 knowledge_items.id
    source_domain   TEXT,                        -- 来源 domain (如 security, ai)
    status          TEXT NOT NULL DEFAULT 'pending' CHECK(status IN (
                        'pending', 'reviewed', 'applied', 'dismissed'
                    )),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    reviewed_at     TEXT,
    notes           TEXT,
    UNIQUE(project_id, tech_name)
);

CREATE INDEX IF NOT EXISTS idx_cg_drift_status ON cg_drift_assessments(status);