-- 033_v1.7_unified_fts.sql: Phase 1 统一搜索 FTS5 视图
-- PRD §3.2.12 / §6.8
-- 注意: FTS5 虚拟表 + 视图, Phase 1 仅建结构, 查询服务在后续 Task 实现

CREATE VIRTUAL TABLE IF NOT EXISTS unified_fts USING fts5(
    entity_type,
    entity_id,
    title,
    summary,
    content,
    tokenize='unicode61'
);

-- 统一搜索视图: 聚合 hotspots + knowledge_items (Phase 1 仅 hotspots)
-- 注意: SQLite 视图不能直接 UNION 不同列数, 这里用统一列名
CREATE VIEW IF NOT EXISTS unified_search AS
SELECT
    'hotspot' AS entity_type,
    h.id AS entity_id,
    h.title AS title,
    h.summary AS summary,
    '' AS content,
    h.category AS category,
    h.ingested_at AS ingested_at
FROM hotspots h
UNION ALL
SELECT
    'knowledge' AS entity_type,
    k.id AS entity_id,
    k.title AS title,
    k.topic AS summary,
    '' AS content,
    k.domain AS category,
    k.ingested_at AS ingested_at
FROM knowledge_items k;
