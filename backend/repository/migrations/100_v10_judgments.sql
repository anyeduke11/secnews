-- 100_v10_judgments.sql
-- v1.0 T11 有证据的判断流程 (SK-02 cve-impact-brief 主路径)
--   对应 contracts.md §5 (Judgment) + §5.2 (EvidenceRef frozen) + §5.3 (状态机 draft→published→superseded/retracted)
--
-- 设计: 新建 v1_judgments 主表 (16 字段) + 扩 v1_case_judgments 为多对多关联
--   - v1_judgments 完整字段 (id, claim, evidence_refs_json, content_hash, ...)
--   - v1_case_judgments 仅 (case_id, judgment_id, composite PK) — 跨 case 关联留扩展空间
--   - 不动 098 v1_case_judgments 已有的 (id, case_id, created_at) — 加 ALTER 兼容

-- v1_judgments 主表: 完整 Judgment 实体
CREATE TABLE IF NOT EXISTS v1_judgments (
    id              TEXT PRIMARY KEY,                       -- ULID ^[A-Z2-7]{26}$
    case_id         TEXT NOT NULL,                          -- 主 case (合同级单 case 关联)
    subject_id      TEXT,                                   -- 关联关注对象 (可选)
    claim_type      TEXT NOT NULL,                          -- finding|assessment|recommendation|warning|hypothesis
    claim           TEXT NOT NULL,                          -- Markdown, ≤ 10KB (服务层校验)
    conditions      TEXT NOT NULL DEFAULT '',               -- 适用条件 (Markdown)
    confidence      TEXT NOT NULL DEFAULT 'medium',         -- low|medium|high|proved
    evidence_refs_json    TEXT NOT NULL DEFAULT '[]',       -- EvidenceRef list, ≥1
    counter_evidence_refs_json TEXT NOT NULL DEFAULT '[]',  -- EvidenceRef list (反证)
    unknowns_json   TEXT NOT NULL DEFAULT '[]',             -- 未知项 (baseline §5 硬约束)
    status          TEXT NOT NULL DEFAULT 'draft',          -- draft|published|superseded|retracted
    content_hash    TEXT,                                   -- sha256 of claim+conditions+evidence
    wiki_path       TEXT,                                   -- publish 时落 wiki path
    revision        INTEGER NOT NULL DEFAULT 1,
    published_at    TEXT,                                   -- publish 时戳 (客户端不传)
    allowed_actions_json TEXT NOT NULL DEFAULT '[]',
    reason          TEXT,                                   -- 服务端推导 reason (e.g. "E_HASH_MISMATCH")
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_v1_judg_case ON v1_judgments(case_id);
CREATE INDEX IF NOT EXISTS idx_v1_judg_status ON v1_judgments(status);
CREATE INDEX IF NOT EXISTS idx_v1_judg_published ON v1_judgments(published_at DESC) WHERE published_at IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uniq_v1_judg_case_claimtype_published
    ON v1_judgments(case_id, claim_type)
    WHERE status = 'published';

-- 扩 v1_case_judgments (T08 098 已建 id/case_id/created_at): 加 judgment_id 字段 + 关联 PK
-- 多对多: 1 judgment 可关联多 case (如跨产品对比); 1 case 可有多 judgment (不同 claim_type)
ALTER TABLE v1_case_judgments ADD COLUMN judgment_id TEXT REFERENCES v1_judgments(id);
CREATE INDEX IF NOT EXISTS idx_v1_case_j_judg ON v1_case_judgments(judgment_id);
CREATE UNIQUE INDEX IF NOT EXISTS uniq_v1_case_j_pair ON v1_case_judgments(case_id, judgment_id)
    WHERE judgment_id IS NOT NULL;
