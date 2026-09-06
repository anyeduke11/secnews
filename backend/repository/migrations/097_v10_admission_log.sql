-- 097_v10_admission_log.sql
-- v1.0 T07: 准入审计 + 人工标注集 — admission_log / admission_label / admission_set
-- 对应 v1_admission_service.quarantine + label/create_label_set/add_to_set/get_set_items
--
-- 4 表 + 3 索引, 全部 IF NOT EXISTS 幂等; 不上 SQL CHECK 约束以保持 evolution 弹性
-- (与现有 90+ 表一致, 业务校验走 service)

-- 准入审计: 每次 evaluate + quarantine 决策的不可变记录
-- 字段对齐 v1_admission_service.quarantine 已写入 SQL:
--   material_id, body_hash (sha256 of url|id), verdict, reason,
--   matched_rule_id (info_filter_rules.id), raw_material_json, created_at
CREATE TABLE IF NOT EXISTS admission_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id         TEXT NOT NULL,
    body_hash           TEXT NOT NULL,
    verdict             TEXT NOT NULL,  -- allow|deny|neutral (AdmissionVerdict.value)
    reason              TEXT NOT NULL,
    matched_rule_id     INTEGER,        -- nullable (NEUTRAL/无规则命中)
    raw_material_json   TEXT NOT NULL DEFAULT '{}',
    created_at          TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_admission_log_material
    ON admission_log(material_id);
CREATE INDEX IF NOT EXISTS idx_admission_log_verdict
    ON admission_log(verdict);
CREATE INDEX IF NOT EXISTS idx_admission_log_created
    ON admission_log(created_at DESC);

-- 人工标注: 单条 material 的 8 维 label (ANNOTATION_DIMENSIONS)
-- 一条 material 同一维度可有多条 (不同时期不同标注者), 因此不强制 UNIQUE(material_id, dimension)
-- 监督批次留 T07 后续 — 当前仅单人标注, 后续接 2 人独立 + agreement 计算
CREATE TABLE IF NOT EXISTS admission_label (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id TEXT NOT NULL,
    dimension   TEXT NOT NULL,  -- entity_type|confidence|urgency|domain|impact|severity|audience|actionability
    value       TEXT NOT NULL,  -- 必须在 ANNOTATION_DIMENSIONS[dimension] 之内 (service 校验)
    annotator   TEXT NOT NULL,  -- human:<name> | agent:<id>
    confidence  REAL NOT NULL DEFAULT 0.9 CHECK (confidence BETWEEN 0.0 AND 1.0),
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_admission_label_material
    ON admission_label(material_id);
CREATE INDEX IF NOT EXISTS idx_admission_label_dim_value
    ON admission_label(dimension, value);

-- 标注集元信息: 一次监督批次一个集, item_count 由 service 维护
CREATE TABLE IF NOT EXISTS admission_set (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,  -- e.g. t07-supervisor-v1
    schema_version  TEXT NOT NULL DEFAULT 'v1.0',
    item_count      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 标注集-条目多对多: 同一 material 可被多个集收录
CREATE TABLE IF NOT EXISTS admission_set_items (
    set_id       INTEGER NOT NULL,
    material_id  TEXT NOT NULL,
    label_id     INTEGER NOT NULL,
    PRIMARY KEY (set_id, material_id, label_id),
    FOREIGN KEY (set_id) REFERENCES admission_set(id) ON DELETE CASCADE,
    FOREIGN KEY (label_id) REFERENCES admission_label(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_admission_set_items_set
    ON admission_set_items(set_id);
CREATE INDEX IF NOT EXISTS idx_admission_set_items_material
    ON admission_set_items(material_id);
