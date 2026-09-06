-- 105_v10_knowledge_items_body.sql
-- v1.0 T18 旧 knowledge_items 853 行数据迁移 — schema 补 body 列 (旧表 18 字段无 body)
ALTER TABLE knowledge_items ADD COLUMN body TEXT NOT NULL DEFAULT '';
