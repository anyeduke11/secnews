-- 022_security_graph.sql: v1.5+ Security Knowledge Graph + Terminology
-- PRD: docs/SECURITY_KNOWLEDGE_GRAPH_PRD.md
-- Arch: docs/SECURITY_KNOWLEDGE_GRAPH.md §4 / §5
--
-- 新增 5 张表：
--   security_entities    — 安全实体 (CVE / ATT&CK / 合规 / CWE / product / cpe)
--   security_edges       — 安全语义边 (uses / causes / fixes / requires ...)
--   security_terms       — 术语规范表
--   security_synonyms    — 术语同义词
--   security_taxonomy    — 术语层级
--
-- 扩展现有表：
--   knowledge_concepts   — + entity_type / external_id / external_ref
--   knowledge_items      — + cve_ids / attack_techniques / compliance_refs / threat_actors / products

-- ============================================================================
-- security_entities
-- ============================================================================
CREATE TABLE IF NOT EXISTS security_entities (
    id          TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    name        TEXT NOT NULL,
    description TEXT,
    external_ref TEXT,
    metadata    TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_security_entities_type ON security_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_security_entities_name ON security_entities(name);

-- ============================================================================
-- security_edges
-- ============================================================================
CREATE TABLE IF NOT EXISTS security_edges (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id   TEXT NOT NULL,
    target_id   TEXT NOT NULL,
    edge_type   TEXT NOT NULL,
    weight      REAL DEFAULT 1.0,
    metadata    TEXT,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES security_entities(id),
    FOREIGN KEY (target_id) REFERENCES security_entities(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_security_edge ON security_edges(source_id, target_id, edge_type);
CREATE INDEX IF NOT EXISTS idx_security_edges_source ON security_edges(source_id);
CREATE INDEX IF NOT EXISTS idx_security_edges_target ON security_edges(target_id);

-- ============================================================================
-- security_terms
-- ============================================================================
CREATE TABLE IF NOT EXISTS security_terms (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical     TEXT NOT NULL UNIQUE,
    term_type     TEXT NOT NULL,
    category      TEXT,
    definition    TEXT,
    external_id   TEXT,
    external_ref  TEXT,
    metadata      TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_security_terms_canonical ON security_terms(canonical);
CREATE INDEX IF NOT EXISTS idx_security_terms_type ON security_terms(term_type);

-- ============================================================================
-- security_synonyms
-- ============================================================================
CREATE TABLE IF NOT EXISTS security_synonyms (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    term_id       INTEGER NOT NULL,
    synonym       TEXT NOT NULL,
    locale        TEXT DEFAULT 'zh-CN',
    created_at    TEXT NOT NULL,
    FOREIGN KEY (term_id) REFERENCES security_terms(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_term_synonym ON security_synonyms(term_id, synonym, locale);

-- ============================================================================
-- security_taxonomy
-- ============================================================================
CREATE TABLE IF NOT EXISTS security_taxonomy (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id     INTEGER,
    term_id       INTEGER NOT NULL,
    sort_order    INTEGER DEFAULT 0,
    created_at    TEXT NOT NULL,
    FOREIGN KEY (term_id) REFERENCES security_terms(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_id) REFERENCES security_terms(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_taxonomy_parent_term ON security_taxonomy(parent_id, term_id);

-- ============================================================================
-- 扩展现有表：knowledge_concepts
-- ============================================================================
ALTER TABLE knowledge_concepts ADD COLUMN entity_type TEXT DEFAULT 'generic';
ALTER TABLE knowledge_concepts ADD COLUMN external_id TEXT;
ALTER TABLE knowledge_concepts ADD COLUMN external_ref TEXT;

-- ============================================================================
-- 扩展现有表：knowledge_items
-- ============================================================================
ALTER TABLE knowledge_items ADD COLUMN cve_ids TEXT;
ALTER TABLE knowledge_items ADD COLUMN attack_techniques TEXT;
ALTER TABLE knowledge_items ADD COLUMN compliance_refs TEXT;
ALTER TABLE knowledge_items ADD COLUMN threat_actors TEXT;
ALTER TABLE knowledge_items ADD COLUMN products TEXT;
