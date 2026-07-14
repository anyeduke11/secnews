-- ============================================================================
-- 002_quality.sql — Phase 3.5 quality-gate tables.
--
-- Two new tables:
--   * quality_check_logs — one row per (item, gate) check
--   * source_reputation  — per-source dynamic reputation score
--
-- Idempotent: every CREATE uses IF NOT EXISTS so the migration is safe
-- to re-run inside a single transaction (used by apply_migrations()).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- quality_check_logs: audit log of every gate.check() invocation.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quality_check_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         TEXT NOT NULL,
    gate_name       TEXT NOT NULL,
    passed          INTEGER NOT NULL,                -- 0/1
    score_deduction INTEGER NOT NULL DEFAULT 0,
    flags           TEXT NOT NULL DEFAULT '[]',      -- JSON array
    reason          TEXT,
    error_msg       TEXT,
    checked_at      TEXT NOT NULL,                   -- ISO 8601 UTC
    mode            TEXT NOT NULL DEFAULT 'loose'    -- 'strict'|'loose'
);

CREATE INDEX IF NOT EXISTS idx_qcl_item ON quality_check_logs(item_id, checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_qcl_gate ON quality_check_logs(gate_name, checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_qcl_time ON quality_check_logs(checked_at DESC);

-- ----------------------------------------------------------------------------
-- source_reputation: per-source score; updated by reputation rebuild job.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS source_reputation (
    source       TEXT PRIMARY KEY,
    score        INTEGER NOT NULL DEFAULT 70,         -- 0..100
    blacklist    INTEGER NOT NULL DEFAULT 0,         -- 0/1
    last_updated TEXT NOT NULL,                       -- ISO 8601 UTC
    pass_count   INTEGER NOT NULL DEFAULT 0,
    fail_count   INTEGER NOT NULL DEFAULT 0
);

-- Seed the 5 known source families + a few common per-source names so
-- the source_reputation_gate has a baseline even before any collector
-- has run. Scores start at 70 ("neutral") so newly-discovered sources
-- aren't penalised for being unknown.
INSERT OR IGNORE INTO source_reputation (source, score, blacklist, last_updated, pass_count, fail_count)
VALUES
    ('ai_collector_default', 70, 0, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), 0, 0),
    ('security_collector_default', 70, 0, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), 0, 0),
    ('finance_collector_default', 70, 0, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), 0, 0),
    ('startup_collector_default', 70, 0, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), 0, 0),
    ('bid_collector_default', 70, 0, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), 0, 0);

-- ----------------------------------------------------------------------------
-- quality.* settings defaults
-- ----------------------------------------------------------------------------
-- These are written idempotently so a first run seeds them; subsequent
-- runs respect whatever the operator has stored in the settings table.
INSERT OR IGNORE INTO settings (key, value, updated_at)
VALUES
    ('quality.strict_mode', 'false', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('quality.min_score', '50', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('quality.url_check_sample_rate', '0.1', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('quality.url_check_concurrency', '5', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('quality.url_check_timeout', '8', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('quality.url_check_interval_seconds', '300', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('quality.reputation_interval_seconds', '21600', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('quality.category_keywords.ai',
     '["AI","人工智能","大模型","LLM","GPT","Claude","OpenAI","Anthropic","深度学习","神经网络","机器学习"]',
     strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('quality.category_keywords.security',
     '["漏洞","CVE","安全","勒索","黑客","attack","exploit","malware","phishing","威胁","0day"]',
     strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('quality.category_keywords.finance',
     '["股票","基金","财报","上市公司","央行","汇率","stock","earnings","Fed","利率","GDP","CFA"]',
     strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('quality.category_keywords.startup',
     '["创业","融资","独角兽","众筹","种子轮","A轮","startup","funding","YC","种子","天使","孵化"]',
     strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('quality.category_keywords.bid',
     '["招标","投标","中标","采购","公告","政府采购","tender","bid","procurement","工程","标段","竞标"]',
     strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('quality.category_keywords.github',
     '["github","trending","star-history","repo","awesome","llm","cursor","claude","openai","langchain","rust","agent"]',
     strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
