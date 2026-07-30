-- 023_hotspot_region.sql: Phase 8 标讯地区筛选
-- 在 hotspots 表新增 region 字段，用于标讯地区筛选

ALTER TABLE hotspots ADD COLUMN region TEXT;
CREATE INDEX IF NOT EXISTS idx_hotspot_region ON hotspots(category, region);