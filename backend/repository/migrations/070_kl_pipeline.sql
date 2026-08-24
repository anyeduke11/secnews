-- 070_kl_pipeline.sql
-- SecNews 整合 Phase 0: KL 管线队列 + Token 台账 + Wiki FTS
-- 对接方案: docs/HOTSPOT_SECNEWS_INTEGRATION.md §3

-- KL 管线任务队列
CREATE TABLE IF NOT EXISTS kl_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 5,
    next_run_at TEXT,
    last_error TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(item_id, stage)
);
CREATE INDEX IF NOT EXISTS idx_kl_stage_status ON kl_queue(stage, status, next_run_at);

-- Token 消耗台账
CREATE TABLE IF NOT EXISTS token_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER,
    item_id TEXT,
    model TEXT,
    provider TEXT,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ledger_item ON token_ledger(item_id, created_at);

-- wiki_items 全文检索
CREATE VIRTUAL TABLE IF NOT EXISTS wiki_items_fts USING fts5(
    title, summary, tags, content,
    tokenize='porter unicode61'
);
