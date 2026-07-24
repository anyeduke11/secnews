-- 036_v1.7_hotspot_lifecycle.sql: Phase 5 hotspots.lifecycle 字段
-- 修复 agent_task_consumer_job 查询 WHERE lifecycle = 'signal' 时的 OperationalError.
-- 之前 hotspots 表缺 lifecycle 列, 触发 "table hotspots has no column named lifecycle" 错误.
-- 新列默认 'signal', 与 knowledge_items 语义一致 (PRD §3.2.4 SAG 生命周期).

ALTER TABLE hotspots ADD COLUMN lifecycle TEXT NOT NULL DEFAULT 'signal';
CREATE INDEX IF NOT EXISTS idx_hotspot_lifecycle ON hotspots(lifecycle, ingested_at);
