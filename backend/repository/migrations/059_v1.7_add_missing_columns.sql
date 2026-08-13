-- 059_v1.7_add_missing_columns.sql: 补齐历史库手工 ALTER 过的列
--
-- 背景 (P0 收尾, 修复 19 个既有测试失败):
--   1. digests.last_read_at  — 031_v1.7_digests.sql 建表时遗漏该列,
--      真实库是手工 ALTER 加的; 新库 (纯 migrations 建 schema) 缺失导致
--      digest_service.py 的 SELECT MAX(last_read_at) 报错,
--      test_mode_api / test_phase3/4_acceptance 共 18 个用例失败。
--   2. knowledge_items.attention_score — 从未进入任何迁移 (真实库为
--      手工 ALTER), attention_scorer.batch_score 的 UPDATE 在新库失败,
--      test_attention_scorer 1 个用例失败。
--
-- 幂等性: ALTER TABLE ADD COLUMN 在列已存在时抛 "duplicate column name",
-- 由 db.py 的 apply_migrations 容错 (视为已应用并记录 schema_version),
-- 因此本迁移在"已手工加过列的历史库"上安全, 在新库上正常补列。
ALTER TABLE digests ADD COLUMN last_read_at TEXT;
ALTER TABLE knowledge_items ADD COLUMN attention_score INTEGER DEFAULT 0;
