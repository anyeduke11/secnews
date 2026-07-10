-- v1.3.0 Phase 3: sync_configs 新增 sync_frequency 字段
-- 值: manual / daily / weekly / after_collect
-- 默认 weekly (与 Phase 42 行为一致: 每周一 10:30 Asia/Shanghai)

ALTER TABLE sync_configs ADD COLUMN sync_frequency TEXT DEFAULT 'weekly';

-- 新增 table_conflicts 字段到 sync_history (用于冲突裁决)
-- JSON 格式: {"todos": 2, "skills": 1}
ALTER TABLE sync_history ADD COLUMN table_conflicts TEXT;