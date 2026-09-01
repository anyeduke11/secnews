-- Migration 088 — v0.7 Batch ⑨ B9-3: llm_secrets per-secret 权限位
--
-- 背景
-- ----
-- v0.7 Batch ⑦ 已落地 encryption_keys.role (admin/user 双层主密钥), 但
-- 同一 role 下的 secrets 对所有同 role user 全部可见, 缺乏细粒度.
-- 本批加 llm_secrets.owner_role 字段 (单值): 标记 secret 归属哪个 role,
-- 解密路径上确保 actor role >= owner_role 才能 load (user 不能读 admin 专属).
--
-- 不在 migration 加 RLS (SQLite 触发器级别, 增加复杂度; 应用层 _check_owner
-- 过滤已经足够, 因为 SecretsService 是唯一入口).
--
-- 兼容: 现有 secret 默认为 'admin' (最高权限), 不影响历史数据.
ALTER TABLE llm_secrets ADD COLUMN owner_role TEXT NOT NULL DEFAULT 'admin';
CREATE INDEX IF NOT EXISTS idx_llm_secrets_owner_role ON llm_secrets(owner_role);
