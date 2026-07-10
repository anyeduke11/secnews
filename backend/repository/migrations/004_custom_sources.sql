-- ============================================================================
-- 004_custom_sources.sql — Phase 8 Addendum 需求 8.4: 自定义信源
--
-- 用途
-- ----
-- 用户在 SettingsPanel 手动添加的 URL 信源。
-- 流程：用户输入 URL → 后端 probe 验证 → 解析 <title> + URL 关键词分类
--      → 写入本表（enabled=1, last_check_status="ok"）。
-- 下次 collect_all_job 跑时，collection_service 读取 enabled=1 的记录，
-- 把每条作为 source dict 注入到对应 category 的 collector.sources 列表。
--
-- 幂等性
-- ------
-- 全 IF NOT EXISTS；再次执行时所有 DDL 退化为 no-op。
-- ============================================================================

CREATE TABLE IF NOT EXISTS custom_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL CHECK (category IN ('ai', 'security', 'finance', 'startup', 'bid', 'github')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL,
    last_check_at TEXT,
    last_check_status TEXT,
    last_check_latency_ms REAL DEFAULT 0,
    last_check_title TEXT,
    notes TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_custom_sources_enabled ON custom_sources(enabled);
CREATE INDEX IF NOT EXISTS idx_custom_sources_category ON custom_sources(category);
