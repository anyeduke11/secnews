-- 020_knowledge_folder.sql: preserve Cubox folder metadata in SQLite

ALTER TABLE knowledge_items ADD COLUMN folder TEXT;
