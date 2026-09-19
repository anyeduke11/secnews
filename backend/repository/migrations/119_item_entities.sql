-- 119_item_entities.sql
-- 2026-09-18 方案 B (gate pipeline_ner): t1 LLM 实体抽取落库列 —
-- JSON 数组字符串 (extract_entities → list[str]); 仅落库, 下游消费不在范围。
ALTER TABLE knowledge_items ADD COLUMN entities TEXT;
