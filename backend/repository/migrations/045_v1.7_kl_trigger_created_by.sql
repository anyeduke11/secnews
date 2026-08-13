-- 045_v1.7_kl_trigger_created_by.sql
-- 目的: 扩展 knowledge_links.created_by 的 CHECK 约束, 允许 'trigger' 值
--       (Phase 10 的 T1/T2 触发器写入链接时使用)
-- 来源: .trae/specs/phase10-t1t2-triggers/spec.md §3 + tasks.md Group C

-- SQLite 修改 CHECK 约束需要重建表:
-- 1. Rename old table
-- 2. Create new table with updated CHECK
-- 3. Copy rows
-- 4. Drop old, rename new

PRAGMA foreign_keys = OFF;

ALTER TABLE knowledge_links RENAME TO knowledge_links_old;

CREATE TABLE knowledge_links (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    from_item_id    TEXT NOT NULL,
    to_item_id      TEXT NOT NULL,
    link_type       TEXT NOT NULL CHECK(link_type IN (
        'similar', 'prerequisite', 'extension', 'contradiction', 'source'
    )),
    confidence      REAL DEFAULT 0.5 CHECK(confidence >= 0 AND confidence <= 1),
    created_by      TEXT CHECK(created_by IN ('agent', 'rule', 'manual', 'trigger')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(from_item_id, to_item_id, link_type)
);

INSERT INTO knowledge_links
    (id, from_item_id, to_item_id, link_type, confidence, created_by, created_at)
SELECT id, from_item_id, to_item_id, link_type, confidence, created_by, created_at
FROM knowledge_links_old;

DROP TABLE knowledge_links_old;

CREATE INDEX IF NOT EXISTS idx_kl_from ON knowledge_links(from_item_id);
CREATE INDEX IF NOT EXISTS idx_kl_to ON knowledge_links(to_item_id);

PRAGMA foreign_keys = ON;
