-- 073_v0.6_wiki_items_fts_sync.sql
-- v0.6 Phase 6 commit 2 — wiki_items_fts 索引 + 存量回填
--
-- 背景 (PROGRESS.md): 070_kl_pipeline.sql 创建了 wiki_items_fts (columns=
-- title/summary/tags/content), 但:
--   * 0 行数据 (从未回填)
--   * 0 触发器 (knowledge_items 写入不联动)
--   * 0 同步 job
--   * search_service 完全没有读它 (只读 LIKE 兜底)
--
-- 本迁移:
--   1) DROP & 重 wiki_items_fts — 加 id UNINDEXED 列; knowledge_items 没有
--      summary / content 列, 因此 wiki_items_fts 改为索引现有列: title /
--      topic / tags / type (足够支撑相关度排序)
--   2) 存量回填: SELECT rowid, id, ... FROM warm.knowledge_items INTO
--      wiki_items_fts (注意: warm DB 是 ATTACH 上的, knowledge_items 在
--      warm.knowledge_items)
--   3) 不加 DB 触发器 — SQLite 不允许 trigger 跨 attached database 引用
--      ("trigger cannot reference objects in database warm"). 同步由
--      wiki_items_fts_sync_job 兜底 (collect.py 链式触发 + drift 检测 +
--      全量 rebuild).
--
-- 注意 1: knowledge_items.id 是 TEXT PRIMARY KEY, 而 FTS5 的 rowid 是 INTEGER;
--         这里我们用新加的 `id UNINDEXED` 列携带字符串 ID (与 hotspots_fts
--         模式平行 — hotspots_fts 把 id 当 UNINDEXED 携带, rowid 也独立)。
--         触发器采用 knowledge_items.rowid (内部 rowid, SQLite 自动) 作为
--         FTS5 rowid — search_service 可用 `k.rowid = f.rowid` 直接回查。

-- 1) 重 wiki_items_fts (加 id UNINDEXED 列, content='' 让 wiki_items_fts_sync_job 可用
--    'delete-all' 命令做全量 rebuild; 也保留触发器同步的语义)
-- knowledge_items 现存可索引列: title / topic / tags / type / source /
-- concepts / cve_ids / attack_techniques — 用 4 列足够 (title + topic +
-- tags + type) 提供相关度排序; 更细粒度需要时再扩列
DROP TABLE IF EXISTS wiki_items_fts;
CREATE VIRTUAL TABLE IF NOT EXISTS wiki_items_fts USING fts5(
    id UNINDEXED,
    title,
    topic,
    tags,
    type,
    tokenize='porter unicode61',
    content=''
);

-- 2) 存量回填 — 拆到 wiki_items_fts_sync_job:
--    迁移只建空 FTS 表; 首次运行时若 wiki_items_fts 行数 < knowledge_items
--    行数, job 走 INSERT OR REPLACE 全量 rebuild。
--    (此处不放 SQL 是因为 apply_migrations 在 warm.knowledge_items 未 attach
--     时会抛 "no such table", 而 apply_migrations 的容错白名单只覆盖
--     "duplicate column" 一类; 跨 DB 容错应在 job 层做, 不在 migration 层
--     提早暴露给启动链。)