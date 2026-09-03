-- 091_v08_trigger_tickets_skill_runs.sql
-- v0.8 Phase A (Task A1): trigger-gate 持久化队列 + skill 运行历史统一数据源 (R3)
--
-- 两张表配合 backend/services/trigger_gate/ 包工作:
--
-- 1. trigger_tickets — trigger-gate 持久化队列
--    所有 skill / playbook 触发请求的唯一入口落表 (submit → pending),
--    worker 出队泵按 (priority ASC, id ASC) 原子抢占置 running,
--    执行结束写 done / failed。进程崩溃后靠 reset_stale_running
--    把超时 running 票据重置回 pending (attempts+1) 实现恢复。
--    - priority: 三档优先级 (0=realtime / 1=normal / 2=batch), 只影响
--      出队顺序, 不抢占正在运行的任务 (非抢占语义, R6)
--    - source: 触发来源 (manual / cron / webhook / kl_event / collector_event)
--    - inputs: JSON 序列化的触发入参
--
-- 2. skill_runs — skill 运行历史统一数据源
--    每次 skill 实际执行的 run 记录 (run_id 主键), 承载 phase / result /
--    metrics / error 全生命周期字段, 由 worker 在派发执行时写入,
--    与 trigger_tickets 通过 ticket_id 松耦合关联 (无外键, 允许
--    无票据的内部直跑场景)。前端运行历史 / 审计 / 重放均读此表。

CREATE TABLE IF NOT EXISTS trigger_tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT UNIQUE NOT NULL,
    target_type TEXT NOT NULL CHECK (target_type IN ('skill', 'playbook')),
    target_id TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 1 CHECK (priority IN (0, 1, 2)),
    source TEXT NOT NULL,
    user_id TEXT,
    inputs TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'done', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    enqueued_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    started_at TEXT,
    finished_at TEXT,
    error TEXT
);

-- 出队泵查询索引: WHERE status='pending' ORDER BY priority ASC, id ASC LIMIT 1
CREATE INDEX IF NOT EXISTS idx_trigger_tickets_status_priority
    ON trigger_tickets(status, priority, id);

CREATE TABLE IF NOT EXISTS skill_runs (
    run_id TEXT PRIMARY KEY,
    ticket_id TEXT,
    skill_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    phase TEXT,
    inputs TEXT,
    result TEXT,
    metrics TEXT,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    finished_at TEXT
);

-- 运行历史查询索引: 按 skill 维度倒序拉最近执行记录
CREATE INDEX IF NOT EXISTS idx_skill_runs_skill
    ON skill_runs(skill_id, created_at DESC);
