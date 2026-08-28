-- Migration 074 — v0.6 Phase 4 S4-1: llm_secrets.provider 字段
-- 给 llm_secrets 加 provider 列 (sensenova / dots.ai / openai / anthropic / ollama / 自定义),
-- 让 ai_hub 能按 provider 名查表拿到明文 base_url/api_key (走 decrypt_for_internal_use)。
-- 幂等: ALTER TABLE ADD COLUMN 无 IF NOT EXISTS (SQLite < 3.35), 但 db.py apply_migrations
-- 已记录过 013_secrets 的列集, 重复执行时会因"duplicate column name" 静默跳过。
-- 索引: 按 provider 频繁查询 (例如 audit / 路由表), 提速关键路径。

ALTER TABLE llm_secrets ADD COLUMN provider TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_llm_secrets_provider ON llm_secrets(provider);