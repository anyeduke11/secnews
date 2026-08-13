-- Phase 17: Knowledge chunks + attention tracking
-- PRD §3.3 — 知识库 chunks 分段存储、全文检索与注意力事件追踪

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         TEXT NOT NULL REFERENCES knowledge_items(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    content         TEXT NOT NULL,
    char_start      INTEGER NOT NULL,
    char_end        INTEGER NOT NULL,
    summary         TEXT DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(item_id, chunk_index)
);

-- FTS5 外部内容表: 直接从 knowledge_chunks 读取 content 和 summary
-- 通过 triggers 与 knowledge_chunks 保持同步
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts USING fts5(
    content,
    summary,
    content=knowledge_chunks,
    tokenize='unicode61'
);

CREATE TRIGGER IF NOT EXISTS knowledge_chunks_ai AFTER INSERT ON knowledge_chunks BEGIN
    INSERT INTO knowledge_chunks_fts(rowid, content, summary)
    VALUES (new.id, new.content, new.summary);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_chunks_ad AFTER DELETE ON knowledge_chunks BEGIN
    INSERT INTO knowledge_chunks_fts(knowledge_chunks_fts, rowid, content, summary)
    VALUES ('delete', old.id, old.content, old.summary);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_chunks_au AFTER UPDATE ON knowledge_chunks BEGIN
    INSERT INTO knowledge_chunks_fts(knowledge_chunks_fts, rowid, content, summary)
    VALUES ('delete', old.id, old.content, old.summary);
    INSERT INTO knowledge_chunks_fts(rowid, content, summary)
    VALUES (new.id, new.content, new.summary);
END;

-- 注意力事件表: 追踪用户对知识条目的注意力行为
CREATE TABLE IF NOT EXISTS attention_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         TEXT NOT NULL REFERENCES knowledge_items(id) ON DELETE CASCADE,
    event_type      TEXT NOT NULL,        -- 'view' | 'dwell' | 'scroll' | 'favorite' | 'annotation' | 'share'
    detail_json     TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_ae_item_time ON attention_events(item_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ae_type_time ON attention_events(event_type, created_at);

-- 知识条目注意力分: 聚合信号，0-100 无量纲分数 (幂等)
-- 注: 此列可能已被 v2.0 版本提前添加，此处通过 SELECT 1 跳过以保持幂等
SELECT 1;