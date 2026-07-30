-- migration 046_lifecycle_v2.sql
-- 目的: 将 v1.7 旧 3 阶段 lifecycle 值迁移到 v2.0 5 阶段 (kl:* 前缀)
-- 来源: docs/v2_prd_review.md Patch 3 / docs/hotspot_v2.0_PRD.md B.11.6
-- 状态: 2026-07-27 待 Phase 9 T1 触发器上线后执行（不在开发期提前跑）

UPDATE knowledge_items
SET lifecycle = CASE lifecycle
    WHEN 'signal'         THEN 'kl:raw'
    WHEN 'amplify:tagged' THEN 'kl:refine'
    WHEN 'generate'       THEN 'kl:structure'
    ELSE lifecycle
END,
updated_at = datetime('now')
WHERE lifecycle IN ('signal', 'amplify:tagged', 'generate');

-- 验证：应输出 0（无旧 3 阶段值残留）
SELECT COUNT(*) FROM knowledge_items
WHERE lifecycle IN ('signal', 'amplify:tagged', 'generate');
