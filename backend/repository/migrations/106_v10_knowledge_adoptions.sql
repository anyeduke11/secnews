-- 106_v10_knowledge_adoptions.sql
-- v1.0 C12 R16 修复: 区分 derived_from (旧 v1_knowledge_refs.role='used') 与 adopted_by
--   derived_from: 知识建立时关联的来源 judgment/action (R16 修复前被误统计为复用)
--   adopted_by:   后续不同 case+revision 真正采用本知识 (C12 起点为 0, 每次采用 1 行)
-- 新知识 total 从 0 起算; recall 走新表 JOIN v1_knowledge (status/review_at/expiry_at)
-- 撤回/反证/过期 → 影响活跃事项 (挂 case blocker via knowledge_review_due 机制)

CREATE TABLE IF NOT EXISTS v1_knowledge_adoptions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    knowledge_id    TEXT NOT NULL,
    knowledge_revision INTEGER NOT NULL,                     -- 当时 knowledge.revision
    case_id         TEXT NOT NULL,                          -- 关联 v1_cases.id
    decision        TEXT NOT NULL,                          -- adopted|skipped|rejected
    condition_diff_json TEXT NOT NULL DEFAULT '[]',         -- 与 prerequisites/counter_examples 的差异 (list[{field, expected, actual}])
    outcome         TEXT,                                   -- success|partial|failure|null (采用后用户填)
    outcome_note    TEXT,                                   -- 自由文本
    adopted_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    adopted_by      TEXT,                                   -- user|agent|system
    decided_by      TEXT,                                   -- 谁做出采用决定
    FOREIGN KEY (knowledge_id) REFERENCES v1_knowledge(id),
    FOREIGN KEY (case_id) REFERENCES v1_cases(id),
    UNIQUE (knowledge_id, knowledge_revision, case_id)      -- 同 case+revision 不重复采用
);

CREATE INDEX IF NOT EXISTS idx_v1_kadopt_knowledge ON v1_knowledge_adoptions(knowledge_id, adopted_at DESC);
CREATE INDEX IF NOT EXISTS idx_v1_kadopt_case ON v1_knowledge_adoptions(case_id);
CREATE INDEX IF NOT EXISTS idx_v1_kadopt_decision ON v1_knowledge_adoptions(decision, adopted_at DESC);
CREATE INDEX IF NOT EXISTS idx_v1_kadopt_recent ON v1_knowledge_adoptions(adopted_at DESC);
