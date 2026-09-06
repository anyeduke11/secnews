-- 101_v10_actions_runs_artifacts.sql
-- v1.0 T12 SK-03 inspection-materials 受控行动与验收
--   对应 contracts.md §6 (Action) + §7 (Run) + §8 (Artifact)
-- 字段对齐 Pydantic v1_0_models (Action / Run / Artifact), 含状态机 + 索引
-- 不上 CHECK 约束以保持 evolution 弹性 (与现有 90+ 表一致, 业务校验走 service)

-- v1_actions 主表: 完整 Action 实体
CREATE TABLE IF NOT EXISTS v1_actions (
    id              TEXT PRIMARY KEY,                       -- ULID ^[A-Z2-7]{26}$
    case_id         TEXT NOT NULL,                          -- Case FK
    judgment_id     TEXT NOT NULL,                          -- Judgment FK (必引 published)
    title           TEXT NOT NULL,                          -- ≤ 200
    scope           TEXT,
    plan            TEXT NOT NULL,                          -- Markdown ≤ 50KB
    plan_hash       TEXT NOT NULL,                          -- sha256(plan)
    tool_versions_json TEXT NOT NULL DEFAULT '{}',          -- {tool: version, ...}
    expected_artifacts_json TEXT NOT NULL DEFAULT '[]',     -- ["report", "checklist", ...]
    success_criteria TEXT,
    expires_at      TEXT,                                   -- ISO; null = 长期
    status          TEXT NOT NULL DEFAULT 'planned',        -- 7 态
    approved_by     TEXT,
    approved_at     TEXT,
    rejection_reason TEXT,
    revision        INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    allowed_actions_json TEXT NOT NULL DEFAULT '[]',
    reason          TEXT
);

CREATE INDEX IF NOT EXISTS idx_v1_actions_case ON v1_actions(case_id);
CREATE INDEX IF NOT EXISTS idx_v1_actions_status ON v1_actions(status);
CREATE INDEX IF NOT EXISTS idx_v1_actions_judgment ON v1_actions(judgment_id);
CREATE INDEX IF NOT EXISTS idx_v1_actions_plan_hash ON v1_actions(plan_hash);

-- 扩 v1_case_actions (T08 098 已建 id/case_id/created_at): 加 action_id + 关联
ALTER TABLE v1_case_actions ADD COLUMN action_id TEXT REFERENCES v1_actions(id);
CREATE INDEX IF NOT EXISTS idx_v1_case_a_action ON v1_case_actions(action_id);
CREATE UNIQUE INDEX IF NOT EXISTS uniq_v1_case_a_pair ON v1_case_actions(case_id, action_id)
    WHERE action_id IS NOT NULL;

-- v1_runs 主表: 完整 Run 实体 (含 Step 序列)
CREATE TABLE IF NOT EXISTS v1_runs (
    id              TEXT PRIMARY KEY,                       -- run_<ULID 26>
    action_id       TEXT NOT NULL,                          -- Action FK
    attempt         INTEGER NOT NULL DEFAULT 1,             -- ge=1
    skill_id        TEXT,
    protocol        TEXT NOT NULL,                          -- dsh|pi|direct|mock
    trigger_source  TEXT NOT NULL,                          -- user|agent|system|scheduled|webhook
    idempotency_key TEXT NOT NULL,                          -- 客户端给
    status          TEXT NOT NULL DEFAULT 'queued',          -- 7 态
    inputs_json     TEXT NOT NULL DEFAULT '{}',
    steps_json      TEXT NOT NULL DEFAULT '[]',              -- Step[] (extra=forbid)
    budget_tokens   INTEGER,
    budget_seconds  INTEGER,
    started_at      TEXT,
    finished_at     TEXT,
    duration_ms     INTEGER,
    result_excerpt  TEXT,
    error           TEXT,
    artifact_ids_json TEXT NOT NULL DEFAULT '[]',            -- Artifact.id list
    revision        INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    allowed_actions_json TEXT NOT NULL DEFAULT '[]',
    reason          TEXT
);

CREATE INDEX IF NOT EXISTS idx_v1_runs_action ON v1_runs(action_id);
CREATE INDEX IF NOT EXISTS idx_v1_runs_status ON v1_runs(status);
CREATE INDEX IF NOT EXISTS idx_v1_runs_idem ON v1_runs(action_id, idempotency_key);
-- contracts §7.4: 同一 action + 同一 attempt 只 1 个 Run
CREATE UNIQUE INDEX IF NOT EXISTS uniq_v1_runs_action_attempt ON v1_runs(action_id, attempt);

-- v1_artifacts 主表: 完整 Artifact 实体
CREATE TABLE IF NOT EXISTS v1_artifacts (
    id              TEXT PRIMARY KEY,                       -- ULID ^[A-Z2-7]{26}$
    run_id          TEXT NOT NULL,                          -- Run FK
    kind            TEXT NOT NULL,                          -- report|file|data|chart|code_patch|message
    title           TEXT NOT NULL,                          -- ≤ 200
    content_ref     TEXT,                                   -- wiki path
    content_hash    TEXT NOT NULL,                          -- sha256 of content
    format          TEXT NOT NULL,                          -- md|json|csv|png|...
    size_bytes      INTEGER NOT NULL DEFAULT 0,             -- ge=0
    verified_by     TEXT,
    verified_at     TEXT,
    verified_result TEXT,                                   -- pass|fail|warn
    accepted_by     TEXT,
    accepted_at     TEXT,
    accepted_note   TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',         -- 5 态
    revision        INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    allowed_actions_json TEXT NOT NULL DEFAULT '[]',
    reason          TEXT
);

CREATE INDEX IF NOT EXISTS idx_v1_artifacts_run ON v1_artifacts(run_id);
CREATE INDEX IF NOT EXISTS idx_v1_artifacts_status ON v1_artifacts(status);
CREATE INDEX IF NOT EXISTS idx_v1_artifacts_hash ON v1_artifacts(content_hash);
CREATE INDEX IF NOT EXISTS idx_v1_artifacts_run_hash ON v1_artifacts(run_id, content_hash);
