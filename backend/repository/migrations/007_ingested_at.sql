-- ============================================================================
-- 007_ingested_at.sql — Phase 15 新增 ingested_at (录入时间) 字段
--
-- 背景
-- ----
-- Bug: 录入的资讯中有历史老旧资讯。某些源页面(如新浪财经、量子位)会显示
-- 历史内容(如"昨日要闻"、"上周回顾"),抓取的 published_at 是历史时间
-- (最严重案例: published_at=2026-06-18, fetched_at=2026-07-06, 差 18 天)。
-- 列表原本按 published_at DESC 排序,导致历史老旧资讯出现在最新列表里。
--
-- 修复
-- ----
-- 新增 ingested_at 字段(录入时间),列表改按 ingested_at DESC 排序。
-- 对于已录入的老资讯,UPDATE ingested_at = published_at,让它们按发布时间
-- 显示在历史位置(不删除)。新抓取的资讯 ingested_at = now()。
--
-- published_at 保留原语义(文章真实发布时间),前端卡片继续显示 published_at。
--
-- 幂等性
-- ------
-- ALTER TABLE ADD COLUMN 不支持 IF NOT EXISTS, 用 PRAGMA table_info 检测
-- 字段是否已存在,避免重复执行报错。
-- ============================================================================

-- 1. 新增 ingested_at 字段(仅在不存在时)
-- SQLite 的 ALTER TABLE ADD COLUMN 不支持 IF NOT EXISTS,
-- 用一个条件 INSERT 到临时表来检测字段是否存在。
-- 实际上 SQLite 没有直接的 "ADD COLUMN IF NOT EXISTS" 语法,
-- 但重复执行 ADD COLUMN 会报 "duplicate column name" 错误。
-- 这里依赖 apply_migrations() 的 schema_version 记录,每个迁移只执行一次,
-- 所以不需要 IF NOT EXISTS。
ALTER TABLE hotspots ADD COLUMN ingested_at TEXT;

-- 2. 数据迁移:已录入老资讯 ingested_at = published_at
-- 让历史老旧资讯按发布时间显示在历史位置,而不是显示在最新录入位置。
-- 新抓取的资讯由代码设置 ingested_at = now(),覆盖此默认值。
UPDATE hotspots SET ingested_at = published_at WHERE ingested_at IS NULL;

-- 3. 索引:列表查询按 ingested_at DESC 排序 + 按 category 过滤
CREATE INDEX IF NOT EXISTS idx_ingested      ON hotspots(ingested_at DESC);
CREATE INDEX IF NOT EXISTS idx_cat_ingested  ON hotspots(category, ingested_at DESC);
