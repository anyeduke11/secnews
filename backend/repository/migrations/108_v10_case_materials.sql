-- v0.8.5 D1.2: Case↔Material 证据关联 — 立项携带证据 (spec docs/v0.8.5/V0.8.5_PLAN.md §11 D1)
-- T15 规划的关联表 (signal_service case_id 分支已引用) 在此正式落地:
--   信号立项 (related_signal_ids) 时, 由 CaseService 把 signal.material_id 绑定进 case,
--   判断层 aggregate 即可读出证据材料 (SK-02 evidence 链的输入端).

CREATE TABLE IF NOT EXISTS v1_case_materials (
    case_id     TEXT NOT NULL,
    material_id TEXT NOT NULL,
    signal_id   TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (case_id, material_id)
);

CREATE INDEX IF NOT EXISTS idx_v1_case_mat_case ON v1_case_materials(case_id);
CREATE INDEX IF NOT EXISTS idx_v1_case_mat_mat  ON v1_case_materials(material_id);
