-- ============================================================================
-- 047_ai_security_category.sql — v1.9 新增 'ai_security' (AI 安全) 分类
--
-- 背景
-- ----
-- v1.9 引入 AISecurityCollector (backend/collectors/ai_security_collector.py)
-- 并已把 Category.AI_SECURITY 接入枚举与采集编排, 但 hotspots 表的
-- CHECK 约束仍是 7 分类, 导致 ai_security 条目入库直接触发
-- "CHECK constraint failed"。本迁移把约束扩展为 8 分类。
--
-- 策略
-- ----
-- 沿用 009_tech_category.sql 的「重建表」模式扩展 CHECK 约束
-- (SQLite 不能直接修改 CHECK)。列集合为当前完整 schema:
-- 基础列 + region(023) + tags/last_read_at(034) + lifecycle(036)。
--
-- 幂等性
-- ----
-- hotspots_new 表名 + CREATE IF NOT EXISTS 幂等,
-- apply_migrations() 记录 schema_version 防止重复执行。
-- ============================================================================

-- 1. 新表（含 ai_security 分类, 列集合与 036 之后的 hotspots 完全一致）
CREATE TABLE IF NOT EXISTS hotspots_new (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('ai','ai_security','security','finance','startup','bid','github','tech')),
    published_at TEXT NOT NULL,
    score INTEGER,
    fetched_at TEXT NOT NULL,
    is_fallback INTEGER NOT NULL DEFAULT 0,
    quality_score INTEGER NOT NULL DEFAULT 100,
    quality_flags TEXT NOT NULL DEFAULT '[]',
    quality_checked_at TEXT,
    url_check_status TEXT,
    ingested_at TEXT,
    bid_status TEXT,
    region TEXT,
    tags TEXT DEFAULT '[]',
    last_read_at TEXT,
    lifecycle TEXT NOT NULL DEFAULT 'signal'
);

-- 2. 数据迁移 (显式列名, 避免列序差异)
INSERT OR IGNORE INTO hotspots_new (
    id, title, summary, source, url, category, published_at, score,
    fetched_at, is_fallback, quality_score, quality_flags, quality_checked_at,
    url_check_status, ingested_at, bid_status, region, tags, last_read_at, lifecycle
)
SELECT
    id, title, summary, source, url, category, published_at, score,
    fetched_at, is_fallback, quality_score, quality_flags, quality_checked_at,
    url_check_status, ingested_at, bid_status, region, tags, last_read_at, lifecycle
FROM hotspots;

-- 3. 替换旧表 (级联删除旧表上的触发器; unified_search 视图依赖 hotspots,
--    须先 DROP、末尾重建, 否则 DROP TABLE 报 "error in view unified_search")
DROP VIEW IF EXISTS unified_search;
DROP TABLE IF EXISTS hotspots;
ALTER TABLE hotspots_new RENAME TO hotspots;

-- 4. 索引重建 (与迁移前 sqlite_master 完全一致)
CREATE INDEX IF NOT EXISTS idx_cat_pub     ON hotspots(category, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_pub         ON hotspots(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_fallback    ON hotspots(is_fallback) WHERE is_fallback = 0;
CREATE INDEX IF NOT EXISTS idx_source      ON hotspots(source);
CREATE INDEX IF NOT EXISTS idx_ingested    ON hotspots(ingested_at DESC);
CREATE INDEX IF NOT EXISTS idx_cat_ingested ON hotspots(category, ingested_at DESC);
CREATE INDEX IF NOT EXISTS idx_hotspot_region ON hotspots(category, region);
CREATE INDEX IF NOT EXISTS idx_hotspot_lifecycle ON hotspots(lifecycle, ingested_at);

-- 5. FTS5 mirror 重建
DROP TABLE IF EXISTS hotspots_fts;
CREATE VIRTUAL TABLE hotspots_fts USING fts5(
    id UNINDEXED,
    title,
    summary,
    content='',
    tokenize='unicode61'
);

-- 6. 触发器重建
CREATE TRIGGER IF NOT EXISTS hotspots_ai AFTER INSERT ON hotspots BEGIN
    INSERT INTO hotspots_fts(rowid, title, summary)
        VALUES (new.rowid, new.title, IFNULL(new.summary, ''));
END;

CREATE TRIGGER IF NOT EXISTS hotspots_ad AFTER DELETE ON hotspots BEGIN
    INSERT INTO hotspots_fts(hotspots_fts, rowid)
        VALUES ('delete', old.rowid);
END;

CREATE TRIGGER IF NOT EXISTS hotspots_au AFTER UPDATE ON hotspots BEGIN
    INSERT INTO hotspots_fts(hotspots_fts, rowid)
        VALUES ('delete', old.rowid);
    INSERT INTO hotspots_fts(rowid, title, summary)
        VALUES (new.rowid, new.title, IFNULL(new.summary, ''));
END;

-- 7. 用现有数据回填 FTS5
INSERT INTO hotspots_fts(rowid, title, summary)
SELECT rowid, title, IFNULL(summary, '') FROM hotspots;

-- 8. 重建 unified_search 视图 (定义与 033_v1.7_unified_fts.sql 一致)
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
