-- 098_v10_cases.sql
-- v1.0 T08: Case 表 + 关联 judgment / action 表骨架
--   对应 contracts.md §4 (Case) + §5 (Judgment) + §6 (Action)
--   字段对齐 Pydantic v1_0_models.py: id (ULID ^[A-Z2-7]{26}$), title, question,
--   goal, scope, priority, status, due_at, subject_id, owner_role, revision, closed_at
--   created_at/updated_at 服务端写, 客户端不传
-- 关联表 judgment / action 只落 case_id FK 骨架 — body 字段后续批次 (T11/T13) 加,
--   本批保证 Case 端到端 (服务+API+UI) + 数据库三向打通
-- IF NOT EXISTS 幂等; 不上 CHECK 约束以保持 evolution 弹性 (与现有 90+ 表一致)

CREATE TABLE IF NOT EXISTS v1_cases (
    id                      TEXT PRIMARY KEY,           -- ULID 26 chars ^[A-Z2-7]{26}$
    title                   TEXT NOT NULL,              -- max 120 (Pydantic 校验)
    question                TEXT NOT NULL,              -- max 500
    goal                    TEXT,                       -- nullable
    scope                   TEXT,                       -- nullable
    priority                TEXT NOT NULL DEFAULT 'p2', -- p0|p1|p2|p3
    status                  TEXT NOT NULL DEFAULT 'open', -- open|in_progress|blocked|closed|archived
    due_at                  TEXT,                       -- nullable ISO
    subject_id              TEXT,                       -- FK v1_subjects.id (空表时不强约束)
    owner_role              TEXT NOT NULL DEFAULT 'user', -- user|system|shared
    revision                INTEGER NOT NULL DEFAULT 1,
    closed_at               TEXT,                       -- nullable ISO
    created_at              TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    tags_json               TEXT NOT NULL DEFAULT '[]',
    related_subject_ids_json TEXT NOT NULL DEFAULT '[]',
    related_signal_ids_json  TEXT NOT NULL DEFAULT '[]',
    related_case_ids_json    TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_v1_case_status ON v1_cases(status);
CREATE INDEX IF NOT EXISTS idx_v1_case_priority ON v1_cases(priority);
CREATE INDEX IF NOT EXISTS idx_v1_case_subject ON v1_cases(subject_id);
CREATE INDEX IF NOT EXISTS idx_v1_case_updated ON v1_cases(updated_at DESC);

-- Judgment 关联 (T11 详情批次再扩字段, 本批保证 case_id 维度可达)
CREATE TABLE IF NOT EXISTS v1_case_judgments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id     TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_v1_case_j_case ON v1_case_judgments(case_id);

-- Action 关联 (T13 详情批次再扩字段, 本批保证 case_id 维度可达)
CREATE TABLE IF NOT EXISTS v1_case_actions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id     TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_v1_case_a_case ON v1_case_actions(case_id);