-- 060_v0.4_discovery_source.sql: P5-4 cg_services 增加校验状态标记
--
-- 背景: 服务网格的自动发现 (lsof/docker/pm2) 与用户手动登记无法区分,
-- 拓扑图上无法判断"哪些是系统扫描来的、哪些是用户确认的"。
-- 增加 discovery_source 列:
--   'auto'      — 扫描自动发现 (默认, 历史行)
--   'manual'    — 用户手动登记 / 项目关联
-- 幂等性: ALTER TABLE ADD COLUMN 在列已存在时抛 duplicate column,
-- 由 db.py 的 apply_migrations 容错 (视为已应用)。
ALTER TABLE cg_services ADD COLUMN discovery_source TEXT DEFAULT 'auto';
