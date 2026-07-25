-- 038_v1.7_drop_phase5_tables.sql
-- Phase 7: Option A 清理 — DROP 5 张 Phase 5 内部 agent 表
-- 删表前必须先在 backend/data/dropped_tables_snapshot_2026-07-25.sql 保留快照
-- kv_cache 评估后保留为可选加速层（不主动维护），不在本迁移删除范围

DROP TABLE IF EXISTS knowledge_tasks;
DROP TABLE IF EXISTS agent_heartbeats;
DROP TABLE IF EXISTS agent_task_skills;
DROP TABLE IF EXISTS skill_config;
DROP TABLE IF EXISTS mcp_tool_invocations;
