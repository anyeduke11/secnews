-- ============================================================================
-- 065_wiki_events.sql — v0.5 §18: wiki ↔ DB 事件对应表
--
-- 定位 (docs/v0.5_refactor_plan.md §18.2):
--   llm-wiki-2.0 (.md 文件, 知识真源) 与 SQLite (运营层) 之间的唯一桥梁。
--   每次知识写入/同步/外部 agent 调用在此留痕, db_trace() 可反查
--   一条知识条目是由哪次采集/哪个 agent 产生的。
--
-- 写入方:
--   - knowledge_sync.py 同步 item/concept 时
--   - ai_hub.py 知识写回路径 (v0.5 强约束: 唯一知识写入口)
--   - dsh 外部 CLI agent 调用 (kind='cli_agent_run', §19)
-- ============================================================================

CREATE TABLE IF NOT EXISTS wiki_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,                -- ISO8601 UTC
    kind       TEXT NOT NULL,                -- sync_item | sync_concept | agent_write | cli_agent_run | ...
    wiki_path  TEXT NOT NULL DEFAULT '',     -- 相对 knowledge/ 的路径, 如 items/a1b2c3.md
    db_table   TEXT NOT NULL DEFAULT '',     -- 关联的运营层表, 如 hotspots / knowledge_items
    db_row_id  TEXT NOT NULL DEFAULT '',     -- 关联行主键
    agent      TEXT NOT NULL DEFAULT '',     -- 产生者: collector:bid / agent:dsh / user 等
    payload    TEXT NOT NULL DEFAULT '{}'    -- JSON 扩展字段 (摘要/耗时/来源 URL 等)
);

-- 反查主路径: 按知识文件路径找事件流
CREATE INDEX IF NOT EXISTS idx_we_wiki_path ON wiki_events(wiki_path, ts DESC);
-- 正向追踪: 按运营层表+行找衍生知识
CREATE INDEX IF NOT EXISTS idx_we_db_ref ON wiki_events(db_table, db_row_id);
-- 运维: 按 kind 统计/清理
CREATE INDEX IF NOT EXISTS idx_we_kind_ts ON wiki_events(kind, ts);
