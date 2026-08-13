-- 051_v1.7_drop_kv_cache.sql
-- Phase 15: 删 kv_cache 表，digest 已读状态迁移到 digests.last_read_at
--
-- 注: 此文件对应 v1.7 分支, 已被 v2.0 分支 (051_v2.0_drop_kv_cache)
-- 提前应用。列 last_read_at 已存在, kv_cache 表已删除。此处为幂等空操作。
SELECT 1;