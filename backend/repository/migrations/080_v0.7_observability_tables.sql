-- 080_v0.7_observability_tables.sql
-- v0.7 Observability Batch 1: 通用执行/事件/审计/指标六表。
--
-- 缺口 (docs/Observability_PRD_v1.0.md §1.3, §7):
--   ④ 无通用 job 执行历史 - 仅 collection_runs/catchup_runs/crawler_runs 三类专用
--   ⑤ agent / pi / dsh 执行零记录 - /api/agents/run 一次性信封不落库
--   ⑦ 无写操作审计 - LLM config 写入 / dsh 启停 / settings 改写无痕
--   (api_metrics_hourly / api_events 由批次③建表, 本迁移只建批次①用到的四张)
--
-- TTL 由 maintenance job 清理:
--   job_runs       30d  (jobs/_runtime.py:instrument_job 改造后写入)
--   agent_runs     30d  (agent_bridge.run_agent_task 改造后写入)
--   process_events 14d  (ProcessSupervisor on_event 钩子)
--   audit_log      90d  (后续批次 ④ 启用写入, 本次先建表占位)
--
-- 设计:
--   - job_runs 行由 instrument_job 在 enter 时 INSERT, finally UPDATE 收尾
--     (status=ok/failed + finished_at + error); 失败 finally 必走, 不依赖异常冒泡
--   - agent_runs 同样 enter/finally 双写, protocol=external_cli / builtin_ai_hub
--   - process_events 纯追加, 无 update (事件不可变)
--   - audit_log 纯追加, 写操作幂等可重

CREATE TABLE IF NOT EXISTS job_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id        TEXT    NOT NULL,                -- "collect_all-1735564800" 形式
    job_type      TEXT    NOT NULL,                -- instrument_job 的 job_type
    trace_id      TEXT,                            -- 关联 llm_usage_log / api_events
    started_at    TEXT    NOT NULL,                -- ISO-8601 UTC
    finished_at   TEXT,
    status        TEXT    NOT NULL DEFAULT 'running',  -- running | ok | failed
    duration_ms   INTEGER,
    error         TEXT,                            -- 异常摘要[:500]
    meta_json     TEXT                             -- 调度器附加信息 (可选, JSON 文本)
);
CREATE INDEX IF NOT EXISTS idx_job_runs_job_type_at
  ON job_runs (job_type, started_at);
CREATE INDEX IF NOT EXISTS idx_job_runs_status_at
  ON job_runs (status, started_at);
CREATE INDEX IF NOT EXISTS idx_job_runs_trace
  ON job_runs (trace_id) WHERE trace_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS agent_runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    agent          TEXT    NOT NULL,               -- pi | claude | codex | builtin
    protocol       TEXT    NOT NULL,               -- external_cli | builtin_ai_hub
    task_kind      TEXT,                           -- 调用方语义 (digest / review / ...)
    trigger_source TEXT,                           -- api | scheduler
    trace_id       TEXT,
    started_at     TEXT    NOT NULL,
    finished_at    TEXT,
    status         TEXT    NOT NULL DEFAULT 'running',  -- running | ok | failed
    duration_ms    INTEGER,
    result_excerpt TEXT,                           -- 结果摘录[:500]
    error          TEXT
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_agent_at
  ON agent_runs (agent, started_at);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status_at
  ON agent_runs (status, started_at);
CREATE INDEX IF NOT EXISTS idx_agent_runs_trace
  ON agent_runs (trace_id) WHERE trace_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS process_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,                  -- 受管进程名 (dsh, pi, ...)
    event       TEXT    NOT NULL,                  -- spawn | exit | restart | stop_requested | crash
    pid         INTEGER,
    uptime_s    REAL,
    exit_code   INTEGER,
    detail      TEXT,                              -- 摘要[:500]
    occurred_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_process_events_name_at
  ON process_events (name, occurred_at);
CREATE INDEX IF NOT EXISTS idx_process_events_event_at
  ON process_events (event, occurred_at);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    actor       TEXT    NOT NULL,                  -- web | system | agent:<name>
    action      TEXT    NOT NULL,                  -- llm_config.update | dsh.start | ...
    target      TEXT,                              -- 资源定位 (provider=ollama, name=dsh, ...)
    detail      TEXT,                              -- JSON 文本 (写入参数摘要, 不含明文密钥)
    trace_id    TEXT,
    occurred_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_log_actor_at
  ON audit_log (actor, occurred_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_action_at
  ON audit_log (action, occurred_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_trace
  ON audit_log (trace_id) WHERE trace_id IS NOT NULL;
