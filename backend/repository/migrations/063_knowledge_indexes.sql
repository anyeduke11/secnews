-- ============================================================================
-- 063_knowledge_indexes.sql — P2.5 SQLite 查询计划审计补索引
--
-- 背景: knowledge_items 除主键外无任何索引, 所有 WHERE/ORDER BY 全表扫描:
--   - knowledge_repo.list_items / get_item   ORDER BY ingested_at DESC
--   - KL 触发器 T1-T4 (classify/trigger job)  WHERE lifecycle = ...
--   - domain_coverage()                       WHERE domain = ... / GROUP BY domain
--   - _classify_new_items                     WHERE domain IS NULL ...
--   - content_draft_generation_job            WHERE lifecycle = 'kl:publish' ...
--
-- 随知识积累 (当前 ~4k 行), 这些热路径全表扫描会线性退化。补 3 个索引。
-- ============================================================================

-- 列表排序 (list_items 主查询 + digest/briefing 按时间)
CREATE INDEX IF NOT EXISTS idx_ki_ingested
    ON knowledge_items(ingested_at DESC);

-- KL 生命周期查询 (T1-T4 触发器 / 编辑部 / content_draft_generation)
CREATE INDEX IF NOT EXISTS idx_ki_lifecycle
    ON knowledge_items(lifecycle);

-- 领域过滤 + 覆盖度统计 (domain_coverage / 知识仪表盘按 domain)
CREATE INDEX IF NOT EXISTS idx_ki_domain
    ON knowledge_items(domain);