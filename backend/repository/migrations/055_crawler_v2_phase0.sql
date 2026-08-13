-- Phase 0: Crawler v2 基础设施 — 6 张新表（旁路写入，不改变现有采集逻辑）
-- 并行运行期: 新表只写不读，不影响现有功能
-- 来源: docs/crawler-v2-technical-spec.md §3

-- ============================================================
-- 1. 源注册表 — 替代现有硬编码源配置
-- ============================================================
CREATE TABLE IF NOT EXISTS crawler_sources (
    id                  TEXT PRIMARY KEY,              -- 全局稳定源 ID
    category            TEXT NOT NULL,                 -- 'security' | 'ai' | 'bid' | 'finance' | ...
    name                TEXT NOT NULL,                 -- 人类可读名称
    kind                TEXT NOT NULL DEFAULT 'html',  -- 'rss' | 'json' | 'html' | 'browser' | 'disabled'
    parser_id           TEXT NOT NULL DEFAULT '',      -- 解析器注册名
    url                 TEXT,                          -- 首页/列表页 URL
    feed_url            TEXT,                          -- RSS/Atom URL
    api_url             TEXT,                          -- JSON API URL
    cadence_seconds     INTEGER NOT NULL DEFAULT 300,  -- 抓取周期
    priority            INTEGER NOT NULL DEFAULT 50,   -- 0-100, 高优先先执行
    max_items           INTEGER NOT NULL DEFAULT 50,   -- 单轮上限
    enabled             INTEGER NOT NULL DEFAULT 1,
    use_proxy           TEXT NOT NULL DEFAULT 'auto',  -- 'off' | 'auto' | 'required'
    headers             TEXT,                          -- JSON 自定义请求头
    verify_ssl          INTEGER NOT NULL DEFAULT 1,
    -- 增量抓取缓存
    etag                TEXT,
    last_modified       TEXT,
    last_fetch_at       TEXT,
    -- 健康状态
    last_success_at     TEXT,
    last_yield_at       TEXT,                          -- 最后一次有产出的时间
    last_error          TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    cooldown_until      TEXT,                          -- 冷却结束时间
    health_score        REAL NOT NULL DEFAULT 1.0,     -- 0.0-1.0
    status              TEXT NOT NULL DEFAULT 'active', -- 'active' | 'grace' | 'stale' | 'dead' | 'disabled'
    -- 冷启动标记
    first_fetch         INTEGER NOT NULL DEFAULT 1,    -- 首次抓取全量模式
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cs_category ON crawler_sources(category);
CREATE INDEX IF NOT EXISTS idx_cs_status ON crawler_sources(status);
CREATE INDEX IF NOT EXISTS idx_cs_priority ON crawler_sources(priority);

-- ============================================================
-- 2. 原始抓取数据 — 溯源与正文校验
-- ============================================================
CREATE TABLE IF NOT EXISTS raw_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         TEXT NOT NULL,                     -- hotspots.id 关联
    source_id       TEXT NOT NULL,                     -- crawler_sources.id
    native_id       TEXT DEFAULT '',                   -- 源侧 ID
    title           TEXT NOT NULL,
    url             TEXT NOT NULL,
    summary         TEXT DEFAULT '',
    content         TEXT DEFAULT '',                   -- 原始正文
    content_hash    TEXT DEFAULT '',                   -- SHA256
    published_at    TEXT,
    fetched_at      TEXT NOT NULL DEFAULT (datetime('now')),
    payload_json    TEXT DEFAULT '{}',                 -- 原始响应元数据
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_ri_item_id ON raw_items(item_id);
CREATE INDEX IF NOT EXISTS idx_ri_source_id ON raw_items(source_id);
CREATE INDEX IF NOT EXISTS idx_ri_fetched_at ON raw_items(fetched_at);

-- ============================================================
-- 3. 每源每轮抓取记录 — 观测与统计
-- ============================================================
CREATE TABLE IF NOT EXISTS crawler_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       TEXT NOT NULL,                     -- crawler_sources.id
    category        TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    status          TEXT NOT NULL DEFAULT 'running',   -- 'running' | 'success' | 'partial' | 'failed'
    fetched_count   INTEGER NOT NULL DEFAULT 0,
    accepted_count  INTEGER NOT NULL DEFAULT 0,
    error_msg       TEXT DEFAULT '',
    duration_ms     INTEGER NOT NULL DEFAULT 0,
    parser_version  TEXT DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cr_source_id ON crawler_runs(source_id);
CREATE INDEX IF NOT EXISTS idx_cr_started_at ON crawler_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_cr_status ON crawler_runs(status);

-- ============================================================
-- 4. URL 校验结果 — 全量校验
-- ============================================================
CREATE TABLE IF NOT EXISTS crawl_url_checks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         TEXT NOT NULL,
    url             TEXT NOT NULL,
    final_url       TEXT DEFAULT '',
    status_code     INTEGER,
    title_match_score REAL,
    checked_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cuc_item_id ON crawl_url_checks(item_id);
CREATE INDEX IF NOT EXISTS idx_cuc_checked_at ON crawl_url_checks(checked_at);

-- ============================================================
-- 5. 标讯结构化字段
-- ============================================================
CREATE TABLE IF NOT EXISTS bid_details (
    item_id         TEXT PRIMARY KEY REFERENCES hotspots(id) ON DELETE CASCADE,
    bid_no          TEXT DEFAULT '',
    buyer           TEXT DEFAULT '',
    region          TEXT DEFAULT '',
    budget          TEXT DEFAULT '',
    deadline        TEXT,
    bid_status      TEXT DEFAULT '',
    industry        TEXT DEFAULT '',
    published_at    TEXT,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_bd_bid_no ON bid_details(bid_no);
CREATE INDEX IF NOT EXISTS idx_bd_bid_status ON bid_details(bid_status);
CREATE INDEX IF NOT EXISTS idx_bd_region ON bid_details(region);

-- ============================================================
-- 6. 质量门禁拒绝记录 — 审计视图
-- ============================================================
CREATE TABLE IF NOT EXISTS quality_rejection_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       TEXT NOT NULL,
    item_title      TEXT NOT NULL,
    item_url        TEXT NOT NULL,
    rejected_by     TEXT NOT NULL,                     -- gate 名称
    reason          TEXT NOT NULL,                     -- 拒绝原因
    raw_data        TEXT DEFAULT '',                   -- 原始数据（调试用）
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_qrl_source_id ON quality_rejection_log(source_id);
CREATE INDEX IF NOT EXISTS idx_qrl_rejected_by ON quality_rejection_log(rejected_by);
CREATE INDEX IF NOT EXISTS idx_qrl_created_at ON quality_rejection_log(created_at);