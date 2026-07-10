-- ============================================================================
-- 009_tech_category.sql — Phase 25 P1 新增 'tech' (IT/科技) 分类
--
-- 背景
-- ----
-- P1 信源扩容 (财联社/金十/IT之家/AIhot) 中,IT之家 (ithome.com) 属于
-- IT/科技 领域,既不属于 AI 也不属于 finance/startup/security/github。
-- 强制塞进 AI 会导致 IT 新闻污染 AI 列表。
-- 新建独立 'tech' 分类承载 Solidot/IT之家/稀土掘金/酷安 等 IT 信源。
--
-- 策略
-- ----
-- 沿用 003_github_category.sql 的「重建表」模式扩展 CHECK 约束。
-- SQLite 不能直接修改 CHECK,只能 DROP/重建。
--
-- 幂等性
-- ----
-- hotspots_new 表名 + 重建操作本身已幂等 (CREATE IF NOT EXISTS),
-- apply_migrations() 还会记录 schema_version 防止重复执行。
-- ============================================================================

-- 1. 新表（含 tech 分类）
CREATE TABLE IF NOT EXISTS hotspots_new (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('ai','security','finance','startup','bid','github','tech')),
    published_at TEXT NOT NULL,
    score INTEGER,
    fetched_at TEXT NOT NULL,
    is_fallback INTEGER NOT NULL DEFAULT 0,
    quality_score INTEGER NOT NULL DEFAULT 100,
    quality_flags TEXT NOT NULL DEFAULT '[]',
    quality_checked_at TEXT,
    url_check_status TEXT,
    ingested_at TEXT,
    bid_status TEXT
);

-- 2. 数据迁移 (仅当旧表存在)
INSERT OR IGNORE INTO hotspots_new
SELECT * FROM hotspots
WHERE EXISTS (SELECT 1 FROM hotspots);

-- 3. 替换旧表
DROP TABLE IF EXISTS hotspots;
ALTER TABLE hotspots_new RENAME TO hotspots;

-- 4. 索引重建
CREATE INDEX IF NOT EXISTS idx_cat_pub     ON hotspots(category, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_pub         ON hotspots(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_fallback    ON hotspots(is_fallback) WHERE is_fallback = 0;
CREATE INDEX IF NOT EXISTS idx_source      ON hotspots(source);
CREATE INDEX IF NOT EXISTS idx_ingested    ON hotspots(ingested_at DESC);
CREATE INDEX IF NOT EXISTS idx_cat_ingested ON hotspots(category, ingested_at DESC);

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
