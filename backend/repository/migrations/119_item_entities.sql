-- 119_item_entities.sql
-- 2026-09-18 方案 B (gate pipeline_ner): t1 LLM 实体抽取落库列 —
-- JSON 数组字符串 (extract_entities → list[str]); 仅落库, 下游消费不在范围。
--
-- 2026-09-21 生产启动修复 (DEV-0182/migration 112 同款先例):
-- 018 虽已记账, 但生产 hot.db 中 knowledge_items 表缺失, 且 warm.db 于
-- 2026-09-18 遗失后仅剩 0 字节空文件 (服务层已按"投影缺失"容错, 见
-- wiki_stats_service) — ALTER 报 "no such table: knowledge_items" → 启动即崩。
-- 故先补 CREATE TABLE IF NOT EXISTS: 列序与完整迁移路径产物一致
-- (018 基础 14 列 → folder..attention_score → 105 body)。已建表环境
-- (测试/新库) 此句为 no-op, 行为不变。
CREATE TABLE IF NOT EXISTS knowledge_items (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT,
    domain TEXT,
    topic TEXT,
    type TEXT,
    difficulty TEXT,
    tags TEXT,
    concepts TEXT,
    mastery INTEGER DEFAULT 0,
    compiled INTEGER DEFAULT 0,
    ingested_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    folder TEXT,
    cve_ids TEXT,
    attack_techniques TEXT,
    compliance_refs TEXT,
    threat_actors TEXT,
    products TEXT,
    lifecycle TEXT NOT NULL DEFAULT 'signal',
    news_type TEXT DEFAULT '',
    tech_stack TEXT DEFAULT '[]',
    attention_score INTEGER DEFAULT 0,
    body TEXT NOT NULL DEFAULT ''
);
ALTER TABLE knowledge_items ADD COLUMN entities TEXT;
