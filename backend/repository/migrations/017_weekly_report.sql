-- v1.3.0 Phase 4: 周报数据表
CREATE TABLE weekly_reports (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start        TEXT NOT NULL,
    week_end          TEXT NOT NULL,
    category_summary  TEXT NOT NULL,
    bid_summary       TEXT,
    trend_weekly      TEXT NOT NULL,
    top_items         TEXT NOT NULL,
    source_health     TEXT,
    favorites_insight TEXT,
    ai_insight        TEXT,
    generated_at      TEXT NOT NULL,
    version           TEXT DEFAULT '1.0',
    UNIQUE(week_start)
);
CREATE INDEX idx_wr_week ON weekly_reports(week_start DESC);

-- v1.3.0 Phase 4: 日级趋势快照 (保留历史趋势数据)
CREATE TABLE trend_daily_snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    category      TEXT NOT NULL,
    count         INTEGER NOT NULL,
    UNIQUE(snapshot_date, category)
);
CREATE INDEX idx_tds_date ON trend_daily_snapshots(snapshot_date DESC);