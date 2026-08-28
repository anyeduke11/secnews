-- Phase 4 S4-2 DeepRead 深度分析面板 (四节报告) — deep_reads 表
--
-- 语义: 用户点击 hotspot/cve/wiki 条目时, 触发 HEAVY 档 LLM 生成 4 节结构化分析
-- (摘要 / 影响 / 关联 / 风险), 持久化到 deep_reads 表; 二次访问直接读 cache,
-- force=true 时覆盖。
--
-- 字段选择:
--   - sections_json: 4 节 markdown 原文 + metadata, JSON 串 (避免 SQLite 多列表格)
--   - content_md: 4 节拼起来的完整 markdown, 便于前端一次渲染或下载
--   - provider/model/tokens_in/out/cost_usd/latency_ms: 用量记账 (与 llm_usage_log 平行)
--   - UNIQUE(entity_type, entity_id): 同一实体只一份, force 重生成时 UPDATE
--   - idx_deep_reads_created: 按时间倒序查询 (前端"最近深读"列表)

CREATE TABLE IF NOT EXISTS deep_reads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    content_md TEXT NOT NULL DEFAULT '',
    sections_json TEXT NOT NULL DEFAULT '{}',
    provider TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    tokens_in INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(entity_type, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_deep_reads_created
    ON deep_reads(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_deep_reads_entity
    ON deep_reads(entity_type, entity_id);