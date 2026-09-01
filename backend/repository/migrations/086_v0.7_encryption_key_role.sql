-- 086_v0.7_encryption_key_role.sql
-- T4: encryption_keys 加 role 列 (admin|user), 支持多用户分级

ALTER TABLE encryption_keys ADD COLUMN role TEXT NOT NULL DEFAULT 'admin';
