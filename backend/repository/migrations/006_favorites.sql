-- ============================================================================
-- 006_favorites.sql — Phase 10 收藏表
--
-- 背景
-- ----
-- 用户需求: 在首页加 ⭐ 按钮, 可以收藏资讯/标讯, 在"收藏"面板中查看,
-- 支持按 6 大分类筛选, 支持批量导出 .xlsx (3 列: 信息类型/标题/原文链接).
--
-- 设计要点
-- --------
-- - 单 user 本地系统（无 user_id 字段，足够覆盖单用户场景）
-- - `UNIQUE(hotspot_id)`：同一资讯/标讯只能收藏一次
-- - `hotspot_id` 是逻辑外键 → hotspots.id（不强制 ON DELETE CASCADE，因为
--   hotspots 表当前没有 user-scoped 删除，但保留 hotspot 记录作为历史）
-- - 索引：`favorited_at DESC` 支持"按收藏时间倒序"列表查询；
--   `category` 支持按分类筛选
-- ============================================================================

CREATE TABLE IF NOT EXISTS favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hotspot_id TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    favorited_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_favorites_favorited_at
    ON favorites(favorited_at DESC);

CREATE INDEX IF NOT EXISTS idx_favorites_category
    ON favorites(category);

-- favorites_stats: 辅助聚合表
--   按 category 记录 total_favorites + last_favorited_at
--   用于前端快速显示"每个分类收藏多少条"
CREATE TABLE IF NOT EXISTS favorites_stats (
    category TEXT PRIMARY KEY,
    total_favorites INTEGER NOT NULL DEFAULT 0,
    last_favorited_at TEXT,
    updated_at TEXT NOT NULL
);
