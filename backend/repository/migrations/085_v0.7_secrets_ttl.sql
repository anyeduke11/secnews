-- 085_v0.7_secrets_ttl.sql
-- T3: secrets TTL + 强制轮换提醒 — encryption_keys 加 last_rotated_at

ALTER TABLE encryption_keys ADD COLUMN last_rotated_at TEXT;
