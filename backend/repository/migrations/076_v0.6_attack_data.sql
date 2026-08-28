-- S4-3: ATT&CK 数据嵌入 (STIX 子集) + CWE→Technique 映射表
-- ============================================================================
-- attack_techniques  — MITRE ATT&CK technique 子集 (Top-200, 静态嵌入)
-- attack_cwe_map     — CWE → ATT&CK technique 静态映射 (~150 条)
--
-- 幂等: IF NOT EXISTS + 重复 id 不报错 (idempotent loader 在 attack_loader.py)
-- ============================================================================

CREATE TABLE IF NOT EXISTS attack_techniques (
    id          TEXT    NOT NULL PRIMARY KEY,
    name        TEXT    NOT NULL,
    tactic      TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_attack_techniques_tactic
    ON attack_techniques(tactic);

CREATE TABLE IF NOT EXISTS attack_cwe_map (
    cwe_id       TEXT NOT NULL,
    technique_id TEXT NOT NULL,
    PRIMARY KEY (cwe_id, technique_id)
);

CREATE INDEX IF NOT EXISTS idx_attack_cwe_map_technique
    ON attack_cwe_map(technique_id);
