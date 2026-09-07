-- 107_v10_legacy_mapping.sql
-- v1.0 C13 全量保真迁移 — 旧 ID → 新 ID 稳定映射 (单一真相源, 替换 T16/T18 散落 audit_log)
--
-- 三源 (legacy_source enum):
--   'dev_seed'            — T16 dev_data/seed.json 15 条 (测试样本, 不进生产)
--   'warm.knowledge_items' — T18 生产 warm.db 3800 行 (3797 kl:publish + 1 kl:structure + 2 kl:deduped 排除)
--   'wiki_items'          — llm-wiki-2.0/items/knowledge_*.md 孤儿 (走 frontmatter.id)
--
-- status 4 账 (T18 in-memory 升级为持久):
--   'applied'           — 成功落 v1_knowledge.status='legacy'
--   'awaiting_review'   — 已落 legacy + lifecycle=kl:publish + body 非空 + wiki 命中 → 后台 promote 候选
--   'quarantined'       — body 全空 + wiki 没命中 → 不入 v1_knowledge (留 mapping 行供回溯)
--   'skipped'           — content_hash 命中 v1_knowledge 已有 → 跳过 (幂等)
--   'failed'            — 错误 → error 字段记录
--
-- C13 修复 R11: 旧 knowledge_items body 列空 (migration 105 ADD DEFAULT ''),
-- 不再用 header-only 拼接蒙混, 走 wiki md 匹配 + body 字节数门槛.

CREATE TABLE IF NOT EXISTS v1_legacy_mapping (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    legacy_source   TEXT    NOT NULL,                     -- 'dev_seed' | 'warm.knowledge_items' | 'wiki_items'
    legacy_id       TEXT    NOT NULL,                     -- 旧 ID (T16: KNOW001 / T18: 357d5032ce99 / wiki: frontmatter.id)
    legacy_revision TEXT,                                 -- nullable (旧知识无 revision 概念)
    new_id          TEXT    NOT NULL,                     -- 26 字符 ULID
    new_revision    INTEGER NOT NULL DEFAULT 1,
    content_hash    TEXT    NOT NULL,                     -- sha256(legacy_id + title + source_url + body) 防 T18 撞库
    status          TEXT    NOT NULL,                     -- 'applied' | 'awaiting_review' | 'quarantined' | 'skipped' | 'failed'
    error           TEXT,
    batch_id        TEXT    NOT NULL,                     -- run/transaction id (C13 幂等游标)
    migrated_at     TEXT    NOT NULL,
    UNIQUE(legacy_source, legacy_id, legacy_revision)
);

CREATE INDEX IF NOT EXISTS idx_mapping_new_id      ON v1_legacy_mapping(new_id);
CREATE INDEX IF NOT EXISTS idx_mapping_status      ON v1_legacy_mapping(status);
CREATE INDEX IF NOT EXISTS idx_mapping_batch       ON v1_legacy_mapping(batch_id);
CREATE INDEX IF NOT EXISTS idx_mapping_legacy      ON v1_legacy_mapping(legacy_source, status);

-- v1_knowledge 加 promoted_at + promotion_reason (C13 后台 promote job 落账)
-- 不动 4 态机; 5 态 'legacy' 由 knowledge_service 状态机 (allowed_actions) 守卫
ALTER TABLE v1_knowledge ADD COLUMN promoted_at       TEXT;
ALTER TABLE v1_knowledge ADD COLUMN promotion_reason  TEXT;

-- C13 后台 promote job 状态记录 (UNIQUE 防并发撞库)
CREATE TABLE IF NOT EXISTS v1_legacy_promote_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    new_id       TEXT    NOT NULL,
    from_status  TEXT    NOT NULL,                       -- 'legacy'
    to_status    TEXT    NOT NULL,                       -- 'published'
    reason       TEXT    NOT NULL,                       -- 'lifecycle_kl_publish + body_present + wiki_hit'
    promoted_at  TEXT    NOT NULL,
    promoted_by  TEXT,                                   -- 'system' | user_id
    UNIQUE(new_id, from_status, to_status)
);

CREATE INDEX IF NOT EXISTS idx_promote_log_new_id ON v1_legacy_promote_log(new_id);
CREATE INDEX IF NOT EXISTS idx_promote_log_at     ON v1_legacy_promote_log(promoted_at);
