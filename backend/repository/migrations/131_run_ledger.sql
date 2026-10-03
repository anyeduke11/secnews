-- 131_run_ledger.sql
-- v0.8.6 P1-1 / M1: Run 账本与审批循环 (docs/HOTSPOT_V0.8.6_AI_NATIVE_PRD.md §4.2/§8.1)
-- 1) v1_runs 扩列 plan_json/policy_version/outcome; 2) v1_proposals 新表;
-- 3) command_log 新表 (P1-1 建表, P1-4 命令栏写入消费)。
-- 约定沿用 101: 枚举不在 DDL 上 CHECK (outcome/status), 由 service 业务层校验;
-- 唯一例外 = PRD §8.1 显式要求的 payload_json 64KB 上限 (防大对象入库)。

-- ── 1. v1_runs 扩列 ─────────────────────────────────────────────────
-- outcome 可空: 101 时代历史行 (queued/succeeded) 无账本 outcome;
-- 新 ledger run 由 RunLedgerService 强制写枚举值。
ALTER TABLE v1_runs ADD COLUMN plan_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE v1_runs ADD COLUMN policy_version TEXT;
ALTER TABLE v1_runs ADD COLUMN outcome TEXT;
CREATE INDEX IF NOT EXISTS idx_v1_runs_outcome ON v1_runs(outcome);

-- ── 2. v1_proposals: 提案 (人主律 — 未审批不得成为事实) ─────────────
CREATE TABLE IF NOT EXISTS v1_proposals (
    id                  TEXT PRIMARY KEY,                    -- prop_<26 ULID>
    case_id             TEXT,                                -- judgment_draft 所属 Case; 其他 kind 可空
    source              TEXT NOT NULL,                       -- agent|command|copilot
    kind                TEXT NOT NULL,                       -- judgment_draft|case_suggestion|knowledge_draft|report
    payload_json        TEXT NOT NULL CHECK(length(payload_json) <= 65536),
    evidence_ids_json   TEXT NOT NULL DEFAULT '[]',
    prompt_version      TEXT,
    status              TEXT NOT NULL DEFAULT 'draft',       -- draft|approved|rejected|expired|failed
    error_msg           TEXT,                                -- status=failed: LLM 超时/拒绝原因 (用例A②)
    reject_reason       TEXT,                                -- 人驳回原因 (≤200, service 强制)
    reviewed_by         TEXT,
    reviewed_at         TEXT,
    run_id              TEXT,                                -- 批准后关联 v1_runs.id
    revision            INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_v1_proposals_status ON v1_proposals(status);
CREATE INDEX IF NOT EXISTS idx_v1_proposals_case ON v1_proposals(case_id);
CREATE INDEX IF NOT EXISTS idx_v1_proposals_created ON v1_proposals(created_at);

-- ── 3. command_log: 命令栏 (P1-4 消费) ──────────────────────────────
CREATE TABLE IF NOT EXISTS command_log (
    id          TEXT PRIMARY KEY,                            -- cmd_<26 ULID>
    input_text  TEXT NOT NULL,
    intent      TEXT,
    action_ref  TEXT,                                        -- proposal_id 等动作引用
    run_id      TEXT,
    outcome     TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_command_log_created ON command_log(created_at);
CREATE INDEX IF NOT EXISTS idx_command_log_run ON command_log(run_id);
