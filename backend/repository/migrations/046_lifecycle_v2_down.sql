-- migration 046_lifecycle_v2_down.sql
-- 目的: 回滚 046 migration，将 kl:* 前缀还原为 v1.7 旧 3 阶段值
-- 警告: 仅在 v2.0 5 阶段触发器尚未稳定前使用；若 T1-T4 已产生新 kl:* 状态数据，
--        回滚会破坏 v2.0 引入的新逻辑，谨慎使用。

UPDATE knowledge_items
SET lifecycle = CASE lifecycle
    WHEN 'kl:raw'       THEN 'signal'
    WHEN 'kl:refine'    THEN 'amplify:tagged'
    WHEN 'kl:structure' THEN 'generate'
    ELSE lifecycle
END,
updated_at = datetime('now')
WHERE lifecycle IN ('kl:raw', 'kl:refine', 'kl:structure');

-- 验证：应输出 0（无 kl:* 前缀值残留，假设未引入新阶段数据）
SELECT COUNT(*) FROM knowledge_items
WHERE lifecycle IN ('kl:raw', 'kl:refine', 'kl:structure');
