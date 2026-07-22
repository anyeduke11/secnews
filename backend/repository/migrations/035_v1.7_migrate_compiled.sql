-- 035_v1.7_migrate_compiled.sql: Phase 1 数据迁移 + 种子标签
-- PRD §3.2 / §6.2
-- 将旧 compiled 字段值映射到新 lifecycle 字段, 并写入种子标签.

-- 1. lifecycle 数据迁移 (compiled 列仍保留, 但不再使用)
UPDATE knowledge_items SET lifecycle = CASE
    WHEN compiled = 1 THEN 'generate'
    WHEN compiled = 0 THEN 'amplify:complete'
    ELSE 'signal'
END;

-- 2. hotspots.tags 空值兜底
UPDATE hotspots SET tags = '[]' WHERE tags IS NULL;

-- 3. 种子标签 (PRD §6.2 核心标签集)
INSERT OR IGNORE INTO tags (id, label, type, weight, created_at) VALUES
    ('cve', 'CVE', 'cve', 1.5, '2026-07-22T00:00:00Z'),
    ('cnvd', 'CNVD', 'cve', 1.5, '2026-07-22T00:00:00Z'),
    ('vulnerability', '漏洞', 'technique', 1.0, '2026-07-22T00:00:00Z'),
    ('ai-security', 'AI安全', 'domain', 1.0, '2026-07-22T00:00:00Z'),
    ('network-security', '网络安全', 'domain', 1.0, '2026-07-22T00:00:00Z'),
    ('prompt-injection', 'Prompt注入', 'technique', 1.0, '2026-07-22T00:00:00Z'),
    ('langchain', 'LangChain', 'framework', 1.0, '2026-07-22T00:00:00Z'),
    ('fastapi', 'FastAPI', 'framework', 1.0, '2026-07-22T00:00:00Z'),
    ('llm', 'LLM', 'technique', 1.0, '2026-07-22T00:00:00Z'),
    ('finance', '金融', 'domain', 1.0, '2026-07-22T00:00:00Z'),
    ('startup', '创业', 'domain', 1.0, '2026-07-22T00:00:00Z'),
    ('bid', '招标', 'domain', 1.0, '2026-07-22T00:00:00Z'),
    ('tech', '科技', 'domain', 1.0, '2026-07-22T00:00:00Z'),
    ('github', 'GitHub', 'source', 1.0, '2026-07-22T00:00:00Z');
