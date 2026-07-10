-- ============================================================================
-- 001_init.sql — initial schema for the hotspot-map data layer.
--
-- Conventions
--   * All datetimes stored as ISO-8601 UTC strings in TEXT columns.
--   * Booleans stored as INTEGER 0/1 (SQLite has no native BOOLEAN).
--   * Enumerated string columns carry CHECK constraints matching the
--     Python enums in backend.domain.enums (Category, CollectorStatus).
--   * JSON arrays (e.g. quality_flags) stored as TEXT, parsed by the
--     repository layer.
--
-- Idempotent: every CREATE uses IF NOT EXISTS so the migration is safe
-- to re-run inside a single transaction (used by apply_migrations()).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- hotspots: one row per collected news / hotspot entry.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hotspots (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('ai','security','finance','startup','bid','github')),
    published_at TEXT NOT NULL,                       -- ISO 8601 UTC
    score INTEGER,                                    -- nullable, 0..100
    fetched_at TEXT NOT NULL,                         -- ISO 8601 UTC
    is_fallback INTEGER NOT NULL DEFAULT 0,           -- 0/1
    quality_score INTEGER NOT NULL DEFAULT 100,       -- 0..100
    quality_flags TEXT NOT NULL DEFAULT '[]',         -- JSON array
    quality_checked_at TEXT,                          -- ISO 8601 UTC, nullable
    url_check_status TEXT                             -- pending|verified|mismatch|skipped, nullable
);

-- Hot-path indexes for the main query: "latest items by category".
CREATE INDEX IF NOT EXISTS idx_cat_pub    ON hotspots(category, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_pub        ON hotspots(published_at DESC);

-- Partial index: only "real" (non-fallback) rows are interesting for the
-- "is this a real signal" hot path.
CREATE INDEX IF NOT EXISTS idx_fallback   ON hotspots(is_fallback) WHERE is_fallback = 0;

-- Source-level lookups (e.g. "show everything from AVD this week").
CREATE INDEX IF NOT EXISTS idx_source     ON hotspots(source);

-- ----------------------------------------------------------------------------
-- hotspots_fts: FTS5 mirror of title + summary for full-text search.
-- unicode61 tokeniser supports Chinese without extra dependencies.
-- ----------------------------------------------------------------------------
CREATE VIRTUAL TABLE IF NOT EXISTS hotspots_fts USING fts5(
    id UNINDEXED,
    title,
    summary,
    content='',
    tokenize='unicode61'
);

-- Keep hotspots_fts in sync with hotspots via triggers.
-- NOTE: with content='' (contentless FTS5):
--   * all column values are discarded and the only way to join back to
--     hotspots is via the FTS5 rowid. The triggers explicitly set
--     hotspots_fts.rowid = hotspots.rowid, which lets the repository
--     do `JOIN hotspots_fts f ON f.rowid = h.rowid`.
--   * DELETE / UPDATE statements on hotspots_fts are forbidden; rows
--     can only be removed via the FTS5 'delete' command
--     (`INSERT INTO ft(ft, rowid) VALUES('delete', :rowid)`).
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

-- ----------------------------------------------------------------------------
-- trend_snapshots: 24h heatmap buckets, written periodically.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS trend_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_at TEXT    NOT NULL,         -- ISO 8601 UTC
    hours_ago   INTEGER NOT NULL,         -- 0..23
    category    TEXT    NOT NULL,
    count       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_trend_lookup ON trend_snapshots(hours_ago, category);

-- ----------------------------------------------------------------------------
-- collection_runs: audit log of collector invocations.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS collection_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    category        TEXT    NOT NULL,
    started_at      TEXT    NOT NULL,    -- ISO 8601 UTC
    finished_at     TEXT,                -- ISO 8601 UTC, nullable
    status          TEXT    NOT NULL CHECK (status IN ('success','partial','failed')),
    item_count      INTEGER NOT NULL DEFAULT 0,
    fallback_count  INTEGER NOT NULL DEFAULT 0,
    error_msg       TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_started  ON collection_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_category ON collection_runs(category, started_at DESC);

-- ----------------------------------------------------------------------------
-- settings: simple KV store for runtime configuration / feature flags.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL             -- ISO 8601 UTC
);
