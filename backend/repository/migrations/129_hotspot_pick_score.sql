-- 129_hotspot_pick_score.sql
-- 2026-09-27 四模式重定义 P2 (spec §3.2): 精选评分列。
-- pick_score 可空 — 未评估的旧行 NULL, 精选视图 COALESCE(quality_score) 兜底排序。
ALTER TABLE hotspots ADD COLUMN pick_score REAL;
