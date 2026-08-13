-- 051_v1.7_drop_kv_cache.sql
-- Phase 15: 删 kv_cache 表，digest 已读状态迁移到 digests.last_read_at
--
-- P0 收尾修复: 原实现为 SELECT 1 空操作 (注释声称 v2.0 分支提前应用),
-- 但当前仓库只有 v1.7 序列, 新库 (纯 migrations) 上 kv_cache 由 032 建表后
-- 从未被 drop, 导致 test_phase5_table_cleanup::test_kv_cache_dropped 失败。
-- 改为真正的 DROP: 对已执行过旧 051 的库 (kv_cache 已手工删除, schema_version
-- 已记录 051) 无影响; 对未执行 051 的新库正常删除。
DROP TABLE IF EXISTS kv_cache;
