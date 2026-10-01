-- 130_rejection_explain.sql
-- 2026-10-01 拒收日志人话化 (spec 2026-10-01-rejection-explain §5):
-- LLM 批量解释回填列。可空 — NULL = 待生成/生成失败(下轮重试), 前端词典兜底。
ALTER TABLE quality_rejection_log ADD COLUMN explain TEXT;
