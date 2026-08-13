-- ============================================================================
-- 049_v1.7_planning_actions.sql — Phase 13 知识规划动作表与操作日志表
--
-- 背景
-- ----
-- Phase 13 引入 KnowledgePlanningPanel, 支持对知识条目进行规划动作
-- 管理 (read / review / link / refine / publish), 记录每个动作的状态
-- 流转, 并保留完整的操作日志便于追溯。
--
-- 动作类型
-- --------
-- - read:     阅读 / 了解
-- - review:   评审 / 审核
-- - link:     关联 / 链接到其他知识
-- - refine:   精炼 / 改进
-- - publish:  发布 / 公开
--
-- 状态流转
-- --------
-- pending → in_progress → completed
-- pending → in_progress → dismissed
--
-- 幂等性
-- ----
-- CREATE TABLE IF NOT EXISTS 确保幂等,
-- apply_migrations() 记录 schema_version 防止重复执行。
-- ============================================================================

-- 1. 规划动作表
CREATE TABLE IF NOT EXISTS planning_actions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         TEXT NOT NULL,
    action_type     TEXT NOT NULL CHECK(action_type IN (
                        'read', 'review', 'link', 'refine', 'publish'
                    )),
    priority        INTEGER NOT NULL DEFAULT 5 CHECK(priority BETWEEN 1 AND 10),
    title           TEXT NOT NULL,
    description     TEXT,
    current_stage   TEXT,
    target_stage    TEXT,
    status          TEXT NOT NULL DEFAULT 'pending' CHECK(status IN (
                        'pending', 'in_progress', 'completed', 'dismissed'
                    )),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at    TEXT,
    dismissed_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_planning_actions_status ON planning_actions(status);
CREATE INDEX IF NOT EXISTS idx_planning_actions_item ON planning_actions(item_id);
CREATE INDEX IF NOT EXISTS idx_planning_actions_created ON planning_actions(created_at);

-- 2. 规划动作操作日志表
CREATE TABLE IF NOT EXISTS planning_action_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id       INTEGER REFERENCES planning_actions(id),
    action_type     TEXT NOT NULL,
    item_id         TEXT NOT NULL,
    event           TEXT NOT NULL CHECK(event IN (
                        'created', 'started', 'completed', 'dismissed', 'failed'
                    )),
    detail          TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_planning_action_log_action ON planning_action_log(action_id);