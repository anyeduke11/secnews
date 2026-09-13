-- ============================================================================
-- 116_drop_crm.sql — CRM 业绩座舱域整体删除 (owner 裁决, 2026-09-13)
--
-- 背景
-- ----
-- crm 域 (security-cockpit 方案 C, migration 071 建表) 数据全 0 行 (休眠),
-- owner 裁决整体移出仓库。代码侧同步删除:
--   - backend/api/crm_{common,customers_api,opportunities_api,stats_api}.py
--   - backend/services/crm_stats_service.py
--   - backend/repository/crm_{customer,opportunity}_repo.py
--   - feature_gates.toml `crm` 键 + extensions 注册块 + 前端 /crm 全链路
--
-- 设计要点
-- --------
-- - 按 FK 依赖顺序 DROP: events (引用 opportunities) → opportunities
--   (引用 customers) → customers
-- - DROP TABLE IF EXISTS: SQLite 下表级索引随表自动删除, 无需逐个 DROP INDEX
-- - 幂等: 重复执行无副作用
-- ============================================================================

DROP TABLE IF EXISTS crm_opportunity_events;
DROP TABLE IF EXISTS crm_opportunities;
DROP TABLE IF EXISTS crm_customers;
