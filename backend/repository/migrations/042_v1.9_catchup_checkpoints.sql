-- 042_v1.9_catchup_checkpoints.sql
-- Phase 9: 资讯抓取流程标准化 — 断点续传 + 完整性验证
--
-- 背景: Phase 8 的 catchup_runs 只记录 run 级别进度, 同一 run 重试不能跳过
--       已经成功的源. 同时缺一个结构化的「数据完整性验证」表.
--
-- 设计:
-- 1) catchup_checkpoints: 每源 (per-source) 粒度的断点表
--    - 主键 (run_id, category, source_name) → 一源一行
--    - status: pending / done / failed / skipped
--    - items_count / error_msg
--    - 重试时 WHERE status='done' 跳过
-- 2) collect_validations: 数据完整性验证结果
--    - 一个 run 完成后写入 0..N 条 validation (4 类)
--    - severity: info / warn / error
--    - 不阻塞采集, 供 /api/health 或告警系统读取
--
-- 兼容性: 不修改任何已有表, 仅追加.

-- ---------------------------------------------------------------------------
-- A) catchup_checkpoints: per-source 断点
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS catchup_checkpoints (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL,
    category        TEXT    NOT NULL,
    source_name     TEXT    NOT NULL,
    status          TEXT    NOT NULL CHECK (status IN ('pending', 'done', 'failed', 'skipped')),
    items_count     INTEGER NOT NULL DEFAULT 0,
    started_at      TEXT,
    finished_at     TEXT,
    error_msg       TEXT,
    UNIQUE(run_id, category, source_name)
);

CREATE INDEX IF NOT EXISTS idx_ckpt_run         ON catchup_checkpoints(run_id);
CREATE INDEX IF NOT EXISTS idx_ckpt_status_run  ON catchup_checkpoints(status, run_id);
-- 找最近 run 的成功源 (跨 run 续传): (category, source_name, finished_at DESC)
CREATE INDEX IF NOT EXISTS idx_ckpt_lookup      ON catchup_checkpoints(category, source_name, finished_at DESC);

-- ---------------------------------------------------------------------------
-- B) collect_validations: 数据完整性验证结果
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS collect_validations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL,
    validation_type TEXT    NOT NULL CHECK (validation_type IN (
                            'source_regression',    -- 源退化 (历史有产出, 本次 0)
                            'time_coverage_gap',   -- 时间窗口空隙 (1h+ 无 ingest)
                            'category_anomaly',    -- 分类级总量突增/骤降
                            'cross_source'         -- 跨源一致性 (cluster 覆盖率)
                        )),
    severity        TEXT    NOT NULL CHECK (severity IN ('info', 'warn', 'error')),
    payload         TEXT    NOT NULL,            -- JSON: 检测详情
    detected_at     TEXT    NOT NULL,
    resolved_at     TEXT                        -- 解决时间 (可选)
);

CREATE INDEX IF NOT EXISTS idx_validation_run     ON collect_validations(run_id);
CREATE INDEX IF NOT EXISTS idx_validation_severity ON collect_validations(severity, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_validation_unresolved ON collect_validations(validation_type) WHERE resolved_at IS NULL;
