-- ============================================================================
-- 003_github_category.sql — Phase 6 添加 'github' 分类
--
-- SQLite 不能直接修改 CHECK 约束，因此采用「重建表」策略：
--   1. CREATE TABLE hotspots_new — 同结构 + 扩展 CHECK 约束含 'github'
--   2. INSERT INTO hotspots_new SELECT * FROM hotspots
--   3. DROP TABLE hotspots
--   4. ALTER TABLE hotspots_new RENAME TO hotspots
--   5. 重建所有索引（drop 旧索引会跟着旧表一起）
--   6. 重建 FTS5 mirror + 触发器（保持 hotspots_fts 与 hotspots 同步）
--
-- 幂等性
-- ------
-- hotspots_new 表名用 IF NOT EXISTS + 一次性 rename 操作；再次执行时
-- 旧表已不存在，整个脚本退化为 no-op。
-- ============================================================================

-- 1. 新表（含 github 分类）
CREATE TABLE IF NOT EXISTS hotspots_new (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('ai','security','finance','startup','bid','github')),
    published_at TEXT NOT NULL,
    score INTEGER,
    fetched_at TEXT NOT NULL,
    is_fallback INTEGER NOT NULL DEFAULT 0,
    quality_score INTEGER NOT NULL DEFAULT 100,
    quality_flags TEXT NOT NULL DEFAULT '[]',
    quality_checked_at TEXT,
    url_check_status TEXT
);

-- 2. 数据迁移（仅当旧表存在时）
INSERT OR IGNORE INTO hotspots_new
SELECT * FROM hotspots
WHERE EXISTS (SELECT 1 FROM hotspots);

-- 3. 替换旧表
DROP TABLE IF EXISTS hotspots;
ALTER TABLE hotspots_new RENAME TO hotspots;

-- 4. 索引重建
CREATE INDEX IF NOT EXISTS idx_cat_pub    ON hotspots(category, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_pub        ON hotspots(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_fallback   ON hotspots(is_fallback) WHERE is_fallback = 0;
CREATE INDEX IF NOT EXISTS idx_source     ON hotspots(source);

-- 5. FTS5 mirror 重建（保留表结构，避免触发器重复定义）
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

-- 7. 用现有数据回填 FTS5（保证搜索可用）
INSERT INTO hotspots_fts(rowid, title, summary)
SELECT rowid, title, IFNULL(summary, '') FROM hotspots;
