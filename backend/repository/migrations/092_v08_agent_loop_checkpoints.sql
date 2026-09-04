-- 092_v08_agent_loop_checkpoints.sql
-- v0.8 Phase B (Task B1): agent_loop 五阶段状态机 checkpoint 持久化 (R3)
--
-- 一张表配合 backend/services/agent_loop/ 包工作:
--
-- loop_checkpoints — 每个 run 在每个阶段落地一行, 状态机驱动
--   phase 五阶段: intent / plan / execute / reflect / commit (顺序固定)
--   status 六态:   pending / running / succeeded / partial / failed / skipped
--   payload: 阶段输出 (dict) JSON 序列化, 供:
--     1. 崩溃恢复 — EXECUTE 后进程被杀 → 新进程从 status=running 推断续跑起点
--     2. UI 展示 — SSE 阶段进度 + 详情页历史回放读 payload
--     3. 调试定位 — phase='failed' 落 error, 排查无需再跑
--   UNIQUE(run_id, phase): 同一 run 同一 phase 只可能有一行 (崩溃恢复 INSERT OR REPLACE)
--   created_at: DB localtime, 阶段实际落地时间; 不区分"开始"和"结束" —
--     每个 phase 的 completed_at 由 status=succeeded/partial/failed 的 update 单独写。
--
-- skill_runs.run_id 是 run_id 的外键语义约束 — 我们不显式声明 FK
-- (skill_runs 是运行历史主表, 不参与高频 checkpoint 写; 业务上保证
-- run_id 总是先在 skill_runs 落行再写 checkpoint, 异常路径不写 checkpoint)。
-- CHECK 限定 phase/status 取值, 注册期之外的脏数据进不来。

CREATE TABLE IF NOT EXISTS loop_checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    phase TEXT NOT NULL CHECK (phase IN ('intent', 'plan', 'execute', 'reflect', 'commit')),
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'succeeded', 'partial', 'failed', 'skipped')),
    payload TEXT,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    completed_at TEXT,
    UNIQUE(run_id, phase)
);

-- 崩溃恢复扫描索引: WHERE status='running' ORDER BY created_at ASC LIMIT 1
CREATE INDEX IF NOT EXISTS idx_loop_checkpoints_status
    ON loop_checkpoints(status, created_at);

-- 历史回放按 run 拉全部阶段 (按 phase 顺序稳定: phase 名按字母序即状态机定义序)
CREATE INDEX IF NOT EXISTS idx_loop_checkpoints_run
    ON loop_checkpoints(run_id, phase);
