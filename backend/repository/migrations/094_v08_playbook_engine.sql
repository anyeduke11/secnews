-- 094_v08_playbook_engine.sql
-- v0.8 Phase C C1+C2: Playbook 引擎 + cron 调度
--
-- 两张表配合 backend/services/playbook_engine/ 包工作:
--
-- 1. playbook_schedules — playbook 的 cron 调度定义 (持久化)
--    - playbook_name: 引用 playbook_engine/examples/*.yml 或 codegarden/playbooks/*.yml
--    - cron_spec: 标准 5 字段 cron (minute hour day month weekday) — APScheduler CronTrigger 直读
--    - timezone: IANA 时区名 (默认 Asia/Shanghai); cron 计算用此 TZ
--    - inputs_json: 用户可覆盖的 inputs (JSON); execute 时 merge 到 schema 默认上
--    - enabled: 0/1 软启用 (停用不等价于删, 留 audit + 可重启用)
--    - created_at/updated_at: 本地表时间戳
--    - UNIQUE(playbook_name): 同 playbook 只一条 schedule, 重启用 upsert
--
-- 2. playbook_runs — 实际执行轨迹 (audit / dashboard 用)
--    - run_id: pb-<uuid12> 与 PlaybookRun.run_id 一致
--    - status: succeeded/partial/failed/stopped (4 态)
--    - inputs_json: 执行时实际 inputs (含 override)
--    - steps_json: 各步骤状态 + output + error (R3 风格同 skill_runs)
--    - finished_at + duration_ms: 终态时间 + 总耗时 (R6 1h 上限监控)
--    - error: 终态错误 (partial/failed)

CREATE TABLE IF NOT EXISTS playbook_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    playbook_name TEXT NOT NULL,
    cron_spec TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
    inputs_json TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE(playbook_name)
);

CREATE INDEX IF NOT EXISTS idx_pb_schedule_enabled
    ON playbook_schedules(enabled);

CREATE TABLE IF NOT EXISTS playbook_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    playbook_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('succeeded', 'partial', 'failed', 'stopped')),
    inputs_json TEXT NOT NULL DEFAULT '{}',
    steps_json TEXT NOT NULL DEFAULT '[]',
    started_at TEXT NOT NULL,
    finished_at TEXT,
    duration_ms INTEGER,
    error TEXT,
    UNIQUE(run_id)
);

CREATE INDEX IF NOT EXISTS idx_pb_runs_name_started
    ON playbook_runs(playbook_name, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_pb_runs_status
    ON playbook_runs(status);