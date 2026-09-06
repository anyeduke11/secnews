-- 099_v10_worker_f01_legacy_hold.sql
-- v1.0 T09: 运行协调器 worker_runs/dead_letter 表 + trigger_tickets.status CHECK 扩展
-- (新增 'legacy_hold' 值 — F01 53 pending 收口用, 留 T16 旧数据迁移时再处理)
--
-- 设计:
--   1. trigger_tickets.status CHECK 扩展 — 加 'legacy_hold' (与 pending/running/done/failed 并列)
--      SQLite 无 ALTER CHECK, 走 045 模板: rename → create new → copy → drop old
--   2. worker_runs — WorkerCoordinator 每次消费 + 派发 + 回报的运行事实
--      与 v0.8 skill_runs (skill 实际执行 run 记录) 不同: 本表是协调层统一调度事实,
--      适用于 trigger_gate + ai_hub + case_service 多队列, 留 run_id 反查 ticket/task
--   3. dead_letter — 失败 ≥ max_retries (默认 3) 的任务落表, 审计 + 手工重放入口
--   4. 全部 IF NOT EXISTS 幂等 (重复跑不报错; 部分已存在的列 / 表跳过)

PRAGMA foreign_keys = OFF;

-- ---------------------------------------------------------------------------
-- 1. trigger_tickets.status CHECK 扩展 — 加 'legacy_hold' (F01 53 pending 收口)
-- ---------------------------------------------------------------------------
-- 与 migration 045 (knowledge_links CHECK 扩展) 同款重建流程
ALTER TABLE trigger_tickets RENAME TO trigger_tickets_old;

CREATE TABLE trigger_tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT UNIQUE NOT NULL,
    target_type TEXT NOT NULL CHECK (target_type IN ('skill', 'playbook')),
    target_id TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 1 CHECK (priority IN (0, 1, 2)),
    source TEXT NOT NULL,
    user_id TEXT,
    inputs TEXT,
    -- 扩展 'legacy_hold' — F01 53 pending 收口用 (T09 legacy_hold_service 落)
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'running', 'done', 'failed', 'legacy_hold'
    )),
    attempts INTEGER NOT NULL DEFAULT 0,
    enqueued_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    started_at TEXT,
    finished_at TEXT,
    error TEXT
);

INSERT INTO trigger_tickets
    (id, ticket_id, target_type, target_id, priority, source, user_id,
     inputs, status, attempts, enqueued_at, started_at, finished_at, error)
SELECT id, ticket_id, target_type, target_id, priority, source, user_id,
     inputs, status, attempts, enqueued_at, started_at, finished_at, error
FROM trigger_tickets_old;

DROP TABLE trigger_tickets_old;

-- 出队泵查询索引重建 (与 migration 091 同款)
CREATE INDEX IF NOT EXISTS idx_trigger_tickets_status_priority
    ON trigger_tickets(status, priority, id);

-- legacy_hold 收口用索引 (T09 legacy_hold_service 按 status 查询 pending)
CREATE INDEX IF NOT EXISTS idx_trigger_tickets_status
    ON trigger_tickets(status);

-- ---------------------------------------------------------------------------
-- 2. worker_runs — WorkerCoordinator 统一运行事实
-- ---------------------------------------------------------------------------
-- task_type: trigger_ticket (skill/playbook) / ai_hub_call / case_service_run /
--   后续 task 接入扩展枚举值即可, 不在本批锁死
-- status: 与 v1_0_models.RunStatus 对齐 (queued/claimed/running/succeeded/failed/cancelled/timed_out),
--   本表只取 worker 层关心的 5 态: queued/claimed/running/succeeded/failed
-- payload_json: 任务入参 (与 trigger_tickets.inputs JSON 字符串同款语义)
-- last_error: 失败原因 (异常类名 + message); attempts=max_retries 时落 dead_letter
CREATE TABLE IF NOT EXISTS worker_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT UNIQUE NOT NULL,
    task_type TEXT NOT NULL,
    queue_name TEXT NOT NULL,
    source_task_id TEXT,
    payload_json TEXT,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN (
        'queued', 'claimed', 'running', 'succeeded', 'failed'
    )),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    started_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    finished_at TEXT,
    duration_ms INTEGER
);

CREATE INDEX IF NOT EXISTS idx_worker_runs_status_at
    ON worker_runs(status, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_worker_runs_queue_status
    ON worker_runs(queue_name, status);
CREATE INDEX IF NOT EXISTS idx_worker_runs_task
    ON worker_runs(task_type, source_task_id) WHERE source_task_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3. dead_letter — 失败 ≥ max_retries (默认 3) 任务的死信表
-- ---------------------------------------------------------------------------
-- original_task_id: 业务侧 task id (trigger_ticket / ai_hub / case), 不带外键约束
--   (允许跨队列异构 id 字符串; 留反查入口给死信重放 UI)
-- error_msg: 最后一次失败原因; attempts: 失败次数 (与 worker_runs.attempts 对齐)
CREATE TABLE IF NOT EXISTS dead_letter (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_task_id TEXT NOT NULL,
    queue_name TEXT NOT NULL,
    task_type TEXT NOT NULL,
    error_msg TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_dead_letter_task
    ON dead_letter(original_task_id);
CREATE INDEX IF NOT EXISTS idx_dead_letter_queue_at
    ON dead_letter(queue_name, created_at DESC);

PRAGMA foreign_keys = ON;
