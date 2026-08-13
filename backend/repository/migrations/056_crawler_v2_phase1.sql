-- Phase 1: crawler-v2 迁移占位（编号补齐 056），无 schema 变更
-- 说明: crawler-v2 按 055 (Phase 0) → 056 (Phase 1) → 057 (Phase 3) 分段推进。
--       本文件仅为恢复迁移编号连续性 (apply_migrations 按文件名排序执行,
--       056 缺失会导致 055 之后直接跳 057 的断号告警)。
--       Phase 1 的实际 schema 变更待实现落地时补充, 届时请直接扩展本文件
--       (或替换占位内容), 不要新建同名迁移。
-- 幂等: 本文件可安全重复执行 (占位表 IF NOT EXISTS)。
-- 来源: docs/crawler-v2-technical-spec.md §5 迁移策略

-- 无操作占位表: 仅用于确认本迁移已被 schema_version 记录;
-- 无业务语义, 可安全忽略, 后续可随 Phase 1 正式实现一并移除。
CREATE TABLE IF NOT EXISTS _migration_056_placeholder (
    id INTEGER PRIMARY KEY
);
