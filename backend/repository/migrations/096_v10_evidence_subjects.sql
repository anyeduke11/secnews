-- 096_v10_evidence_subjects.sql
-- v1.0 T05-B: 关注对象 (Subject) + 资料 (Material) + 信号 (Signal) 三表
--   + 提交键 (submission_key) + 证据收据 (evidence_receipts) 配套
-- 对应 contracts.md §1 (Subject) §2 (Material) §3 (Signal)
-- 字段对齐 Pydantic v1_0_models.py; revision 状态机由 service 层推导
-- 不上 SQL CHECK 约束以保持 evolution 弹性 (与现有 90+ 表一致, 业务校验走 service)

-- 关注对象: 任何被持续关注的实体 (CVE / 产品 / 厂商 / 人物 / 资产 ...)
CREATE TABLE IF NOT EXISTS v1_subjects (
    id              TEXT PRIMARY KEY,
    entity_type     TEXT NOT NULL,  -- SubjectEntityType enum: cve|product|vendor|person|asset|cve_product|asset_group|other
    canonical_name  TEXT NOT NULL,
    aliases_json    TEXT NOT NULL DEFAULT '[]',  -- 别名数组
    importance      TEXT NOT NULL DEFAULT 'normal',  -- SubjectImportance: critical|high|normal|low
    tags_json       TEXT NOT NULL DEFAULT '[]',
    related_subject_ids_json TEXT NOT NULL DEFAULT '[]',
    first_seen_at   TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    revision        INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_v1_subj_type ON v1_subjects(entity_type);
CREATE INDEX IF NOT EXISTS idx_v1_subj_importance ON v1_subjects(importance);
CREATE INDEX IF NOT EXISTS idx_v1_subj_last_seen ON v1_subjects(last_seen_at DESC);

-- 资料: 一份独立的可引用证据 (URL / 公告 / 漏洞库条目 / 内部文件 ...)
CREATE TABLE IF NOT EXISTS v1_materials (
    id              TEXT PRIMARY KEY,
    source_kind     TEXT NOT NULL,  -- url|html|pdf|email|note|file|api|other
    url             TEXT,           -- 原始 URL (脱敏后入库, 不要求非空)
    title           TEXT NOT NULL,
    content_hash    TEXT NOT NULL,  -- sha256 of normalized content
    content_length  INTEGER NOT NULL,
    content_ref     TEXT,           -- 仓库路径 (相对 WIKI_ROOT) 或外部 storage key
    summary         TEXT,           -- 摘要 (可由 LLM 生成或人工填写)
    published_at    TEXT,           -- 原始发布时间 (nullable)
    fetched_at      TEXT NOT NULL,
    fetched_by      TEXT,           -- agent_id / user_id / system
    subject_ids_json TEXT NOT NULL DEFAULT '[]',  -- 关联关注对象
    metadata_json   TEXT NOT NULL DEFAULT '{}',  -- 自由扩展字段
    revision        INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_v1_mat_hash ON v1_materials(content_hash);
CREATE INDEX IF NOT EXISTS idx_v1_mat_fetched ON v1_materials(fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_v1_mat_published ON v1_materials(published_at DESC);

-- 信号: 一次准入评估后产出的"值得关注的提示"
CREATE TABLE IF NOT EXISTS v1_signals (
    id              TEXT PRIMARY KEY,
    subject_id      TEXT NOT NULL,
    material_id     TEXT NOT NULL,
    summary         TEXT NOT NULL,
    occurred_at     TEXT NOT NULL,
    admission_rule_version TEXT NOT NULL,
    admission_reason TEXT NOT NULL DEFAULT '',
    supersedes_signal_id TEXT,  -- 旧信号 ID (新版本替代旧版)
    confidence      TEXT NOT NULL DEFAULT 'unverified',  -- verified|likely|unverified
    status          TEXT NOT NULL DEFAULT 'unverified',  -- 同上 enum
    revision        INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (subject_id) REFERENCES v1_subjects(id),
    FOREIGN KEY (material_id) REFERENCES v1_materials(id)
);
CREATE INDEX IF NOT EXISTS idx_v1_sig_subject ON v1_signals(subject_id);
CREATE INDEX IF NOT EXISTS idx_v1_sig_material ON v1_signals(material_id);
CREATE INDEX IF NOT EXISTS idx_v1_sig_occurred ON v1_signals(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_v1_sig_confidence ON v1_signals(confidence);
CREATE INDEX IF NOT EXISTS idx_v1_sig_supersedes ON v1_signals(supersedes_signal_id);

-- 提交键: (subject_id, source, external_id) 唯一 — 同源同实体不重复创建关注对象
-- 实现 contracts.md §0.5 幂等: 同一提交键 + 期望 body 哈希 → 已有 receipt
CREATE TABLE IF NOT EXISTS v1_subject_identifiers (
    subject_id      TEXT NOT NULL,
    source          TEXT NOT NULL,  -- nvd|cnvd|cnnvd|github|internal|manual
    external_id     TEXT NOT NULL,
    first_seen_at   TEXT NOT NULL,
    PRIMARY KEY (source, external_id),
    FOREIGN KEY (subject_id) REFERENCES v1_subjects(id)
);
CREATE INDEX IF NOT EXISTS idx_v1_subj_id_subject ON v1_subject_identifiers(subject_id);

-- 证据收据: 每次提交 (subject/material/signal) 的回执 — 不可变
-- 实现 contracts.md §0.5 idempotency_key + body hash
CREATE TABLE IF NOT EXISTS v1_evidence_receipts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_key  TEXT NOT NULL,  -- idempotency_key
    body_hash       TEXT NOT NULL,  -- sha256 of canonical request body
    entity_type     TEXT NOT NULL,  -- subject|material|signal
    entity_id       TEXT NOT NULL,
    submitted_by    TEXT NOT NULL,  -- agent_id|user_id|system
    intent_id       TEXT,           -- 提交意图 (允许 pending 状态, 见 service)
    status          TEXT NOT NULL DEFAULT 'committed',  -- committed|rolled_back|superseded
    submitted_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    extra_json      TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_v1_recv_key ON v1_evidence_receipts(submission_key);
CREATE INDEX IF NOT EXISTS idx_v1_recv_entity ON v1_evidence_receipts(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_v1_recv_status ON v1_evidence_receipts(status);
-- 幂等唯一性: 同一 submission_key + body_hash 不应重复 commit
CREATE UNIQUE INDEX IF NOT EXISTS uniq_v1_recv_key_hash
    ON v1_evidence_receipts(submission_key, body_hash);
