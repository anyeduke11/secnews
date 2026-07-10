-- ============================================================================
-- 005_source_stats.sql — Phase 9 招标源质量: 每个数据源 (source_name + category)
-- 累计产出统计 + 零产出次数 + 健康状态。
--
-- 背景
-- ----
-- Phase 9 用户反馈: 招标资讯只有少数来源覆盖，需要识别出长期无产出的
-- "死源"，并报告每个分类下的源覆盖度，避免出现热点信息只来自少数源。
--
-- 表结构
-- ------
--   source_stats: 1 行 = 1 个 source_name (在 1 个 category 下)
--   累计 total_runs / zero_yield_runs / total_items_collected
--   最后成功时间 last_seen_at，最后任意时间 last_checked_at
--   健康状态 status: 'active' | 'stale' | 'dead'
--     - active: 最近 1 次 collect 有产出
--     - stale: 连续 3 次以上 zero_yield (单次抖动不算死)
--     - dead: 连续 6 次以上 zero_yield (说明源根本不可用)
--
-- quality_settings
-- ---------------
--   新增 3 个配置:
--     quality.coverage_min_active_sources: 每分类最少活跃源数 (默认 3)
--     quality.coverage_max_zero_yield_runs: 多少连 0 才升级为 stale (默认 3)
--     quality.coverage_dead_threshold: 多少连 0 才标 dead (默认 6)
--
-- 幂等性
-- ------
-- IF NOT EXISTS + ON CONFLICT；可重复执行。
-- ============================================================================

CREATE TABLE IF NOT EXISTS source_stats (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    category            TEXT NOT NULL,
    source_name         TEXT NOT NULL,
    source_url          TEXT NOT NULL,
    last_seen_at        TEXT,                          -- 最近一次产出 >=1 item 的时间
    last_checked_at     TEXT,                          -- 最近一次 collect 跑过该源的时间
    total_runs          INTEGER NOT NULL DEFAULT 0,    -- 累计 collect 次数
    zero_yield_runs     INTEGER NOT NULL DEFAULT 0,    -- 连续零产出次数 (每次有产出重置为 0)
    total_items         INTEGER NOT NULL DEFAULT 0,    -- 累计产出 items 数
    last_error          TEXT,                          -- 最近一次错误信息
    status              TEXT NOT NULL DEFAULT 'active' -- active|stale|dead
                      CHECK (status IN ('active','stale','dead')),
    updated_at          TEXT NOT NULL,
    UNIQUE(category, source_name)
);

CREATE INDEX IF NOT EXISTS idx_source_stats_cat
    ON source_stats(category, status);
CREATE INDEX IF NOT EXISTS idx_source_stats_status
    ON source_stats(status, last_checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_source_stats_zero
    ON source_stats(zero_yield_runs DESC)
    WHERE status != 'active';

-- coverage_runs: 每次 collect 跑完后的源覆盖度快照
--   用于追溯"哪次 collect 之后哪条源被标 dead"
CREATE TABLE IF NOT EXISTS coverage_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,                 -- 与 collection_runs 关联
    category        TEXT NOT NULL,
    total_sources   INTEGER NOT NULL DEFAULT 0,    -- 配置源数
    active_sources  INTEGER NOT NULL DEFAULT 0,    -- 本次产出 >=1 item 的源数
    zero_sources    INTEGER NOT NULL DEFAULT 0,    -- 本次产出 0 的源数
    coverage_ratio  REAL NOT NULL DEFAULT 0,       -- active_sources / total_sources
    details_json    TEXT NOT NULL DEFAULT '[]',    -- JSON: 每源状态
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_coverage_runs_run
    ON coverage_runs(run_id, category);
CREATE INDEX IF NOT EXISTS idx_coverage_runs_cat_time
    ON coverage_runs(category, created_at DESC);

-- Settings defaults
INSERT OR IGNORE INTO settings (key, value, updated_at)
VALUES
    ('quality.coverage_min_active_sources', '3',
     strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('quality.coverage_max_zero_yield_runs', '3',
     strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('quality.coverage_dead_threshold', '6',
     strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
