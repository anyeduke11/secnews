-- 102_v10_knowledge.sql
-- v1.0 T13 SK-04/05/06 知识发布/复用/复查
--   对应 contracts.md §9 (Knowledge) + §9.4 (ReuseReceipt 派生) + §9.2 状态机
-- 字段对齐 Pydantic v1_0_models.Knowledge (24 字段, §9.1)
-- 不上 CHECK 约束以保持 evolution 弹性

-- v1_knowledge 主表: 完整 Knowledge 实体
CREATE TABLE IF NOT EXISTS v1_knowledge (
    id              TEXT PRIMARY KEY,                       -- ULID ^[A-Z2-7]{26}$
    kind            TEXT NOT NULL,                          -- 6 态: principle|pattern|anti_pattern|reference|playbook|checklist
    title           TEXT NOT NULL,                          -- ≤ 200
    body            TEXT NOT NULL,                          -- Markdown ≤ 100KB
    prerequisites_json  TEXT NOT NULL DEFAULT '[]',          -- list[str]
    counter_examples_json TEXT NOT NULL DEFAULT '[]',        -- list[str]
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',          -- list[EvidenceRef] (同 §5.2)
    expiry_at       TEXT,                                   -- ISO; null = 长期
    review_at       TEXT,                                   -- ISO; 下次复查时间 (SK-06 触发)
    status          TEXT NOT NULL DEFAULT 'draft',          -- 4 态: draft|published|deprecated|retracted
    revision        INTEGER NOT NULL DEFAULT 1,
    wiki_path       TEXT,                                   -- 不可变 Markdown revision path
    content_hash    TEXT,                                   -- sha256(body + prerequisites + counter_examples + evidence_refs)
    published_at    TEXT,                                   -- publish 时戳
    deprecation_reason TEXT,                                -- deprecate 必填 reason
    replacement_knowledge_id TEXT,                          -- 建议替代 knowledge_id (deprecate 可空)
    retraction_reason TEXT,                                -- retract 必填 reason
    allowed_actions_json TEXT NOT NULL DEFAULT '[]',
    reason          TEXT,                                   -- 服务端推导 reason
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_v1_knowledge_kind ON v1_knowledge(kind);
CREATE INDEX IF NOT EXISTS idx_v1_knowledge_status ON v1_knowledge(status);
CREATE INDEX IF NOT EXISTS idx_v1_knowledge_review ON v1_knowledge(review_at) WHERE status = 'published' AND review_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_v1_knowledge_published ON v1_knowledge(published_at DESC) WHERE status = 'published';

-- v1_knowledge_revisions append-only: 每次 publish/deprecate/retract 留 revision 行
CREATE TABLE IF NOT EXISTS v1_knowledge_revisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    knowledge_id    TEXT NOT NULL,
    revision        INTEGER NOT NULL,
    status          TEXT NOT NULL,                          -- 当时状态
    reason          TEXT,                                   -- deprecate/retract 必填
    wiki_path       TEXT,
    content_hash    TEXT,
    recorded_at     TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    recorded_by     TEXT,                                   -- user|agent|system
    FOREIGN KEY (knowledge_id) REFERENCES v1_knowledge(id)
);
CREATE INDEX IF NOT EXISTS idx_v1_krev_knowledge ON v1_knowledge_revisions(knowledge_id, revision DESC);

-- v1_knowledge_refs 引用关联表 (派生 ReuseReceipt 的物理基础, §9.4)
CREATE TABLE IF NOT EXISTS v1_knowledge_refs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    knowledge_id    TEXT NOT NULL,
    source_type     TEXT NOT NULL CHECK (source_type IN ('judgment', 'action', 'artifact')),
    source_id       TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'used',          -- used|contradicts|extends
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (knowledge_id) REFERENCES v1_knowledge(id),
    UNIQUE (knowledge_id, source_type, source_id, role)
);
CREATE INDEX IF NOT EXISTS idx_v1_krefs_knowledge ON v1_knowledge_refs(knowledge_id);
CREATE INDEX IF NOT EXISTS idx_v1_krefs_source ON v1_knowledge_refs(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_v1_krefs_recent ON v1_knowledge_refs(created_at DESC);
