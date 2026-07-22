-- 030_v1.7_personal_profile.sql: Phase 3 个性化画像
-- PRD §3.2.9
-- 注意: Phase 1 提前建表, 供后续 Phase 3 使用

CREATE TABLE IF NOT EXISTS personal_profile (
    dimension    TEXT PRIMARY KEY,
    weight       REAL DEFAULT 0.0,
    last_updated TEXT NOT NULL,
    decayed_at   TEXT NOT NULL
);
