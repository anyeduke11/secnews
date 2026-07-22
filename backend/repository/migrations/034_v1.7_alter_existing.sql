-- 034_v1.7_alter_existing.sql: Phase 1 现有表字段新增
-- PRD §3.2 / §3.3
-- 注意: ALTER TABLE ADD COLUMN 在 SQLite 无 IF NOT EXISTS,
-- 幂等性由 schema_version 表保证 (每个迁移只执行一次).
-- 若迁移中途失败, 034 部分列可能已加, 需手动处理或重建 DB.

-- hotspots: 标签缓存 + 阅读时间
ALTER TABLE hotspots ADD COLUMN tags TEXT DEFAULT '[]';
ALTER TABLE hotspots ADD COLUMN last_read_at TEXT;

-- knowledge_items: SAG 生命周期 (替换 compiled) + 新闻类型 + 技术栈
ALTER TABLE knowledge_items ADD COLUMN lifecycle TEXT NOT NULL DEFAULT 'signal';
ALTER TABLE knowledge_items ADD COLUMN news_type TEXT DEFAULT '';
ALTER TABLE knowledge_items ADD COLUMN tech_stack TEXT DEFAULT '[]';

-- cg_projects: 技术栈关联
ALTER TABLE cg_projects ADD COLUMN tech_stack_ids TEXT DEFAULT '[]';
