-- 029_v1.7_tech_stack.sql: Phase 2 个人技术栈
-- PRD §3.2.3
-- 注意: Phase 1 提前建表, 供后续 Phase 2 使用

CREATE TABLE IF NOT EXISTS tech_stack (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    category     TEXT,
    proficiency  INTEGER DEFAULT 1,
    notes        TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tech_stack_category ON tech_stack(category);
