-- migration 043_v2.0_fingerprints_scores.sql
-- 目的: Phase 8 复利基础设施 — 跨源去重/AI 评分/实体连接/知识复用关联

-- 1. 跨源去重
CREATE TABLE IF NOT EXISTS content_fingerprints (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    hotspot_id    TEXT NOT NULL REFERENCES hotspots(id) ON DELETE CASCADE,
    simhash       BIGINT NOT NULL,              -- 64-bit simhash
    url_canonical TEXT NOT NULL,                 -- 规范化 URL
    title_norm    TEXT NOT NULL,                 -- 规范化标题
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(hotspot_id)
);
CREATE INDEX IF NOT EXISTS idx_fp_simhash ON content_fingerprints(simhash);
CREATE INDEX IF NOT EXISTS idx_fp_url_canonical ON content_fingerprints(url_canonical);

-- 2. AI 评分
CREATE TABLE IF NOT EXISTS ai_scores (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hotspot_id  TEXT NOT NULL REFERENCES hotspots(id) ON DELETE CASCADE,
    score       REAL NOT NULL CHECK(score >= 0 AND score <= 10),  -- 0-10
    reason      TEXT,                                               -- LLM 可解释理由
    scorer      TEXT,                                               -- 'agent:claude-desktop' / 'agent:cursor' / 'rule'
    scored_at   TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ai_score ON ai_scores(hotspot_id, scored_at);

-- 3. 实体连接
CREATE TABLE IF NOT EXISTS item_entities (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id     TEXT NOT NULL,                    -- knowledge_items.id
    entity_name TEXT NOT NULL,                    -- 如 'prompt-injection'
    entity_type TEXT NOT NULL CHECK(entity_type IN (
        'concept', 'tool', 'vendor', 'person', 'cve', 'technique', 'standard', 'event'
    )),
    confidence  REAL DEFAULT 1.0 CHECK(confidence >= 0 AND confidence <= 1),
    source      TEXT CHECK(source IN ('rule', 'agent', 'manual')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(item_id, entity_name, entity_type)
);
CREATE INDEX IF NOT EXISTS idx_entity_name ON item_entities(entity_name);
CREATE INDEX IF NOT EXISTS idx_item_id ON item_entities(item_id);

-- 4. 知识复用关联（复利核心）
CREATE TABLE IF NOT EXISTS knowledge_links (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    from_item_id    TEXT NOT NULL,
    to_item_id      TEXT NOT NULL,
    link_type       TEXT NOT NULL CHECK(link_type IN (
        'similar', 'prerequisite', 'extension', 'contradiction', 'source'
    )),
    confidence      REAL DEFAULT 0.5 CHECK(confidence >= 0 AND confidence <= 1),
    created_by      TEXT CHECK(created_by IN ('agent', 'rule', 'manual')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(from_item_id, to_item_id, link_type)
);
CREATE INDEX IF NOT EXISTS idx_kl_from ON knowledge_links(from_item_id);
CREATE INDEX IF NOT EXISTS idx_kl_to ON knowledge_links(to_item_id);