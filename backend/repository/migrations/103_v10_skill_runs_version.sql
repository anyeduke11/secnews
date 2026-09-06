-- 103_v10_skill_runs_version.sql
-- v1.0 T17 E2E-10 启停校验: skill_runs 加 version 字段 (T14 SkillDef.version 落库对齐)
ALTER TABLE skill_runs ADD COLUMN version TEXT;
