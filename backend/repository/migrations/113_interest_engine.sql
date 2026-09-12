-- DEV-0182 (2026-09-12): Interest Engine — 内容门禁 L3 × 单用户推荐
-- (PRD: docs/INTEREST_ENGINE_PRD_v1.0.md; owner 三项裁决 2026-09-12)
--
-- 不复用 attention_events (054): 其 FK 绑 knowledge_items 且 30d 清理属
-- 知识注意力语义; 兴趣信号要写入时对 hotspots 做域归因, item 行后续可被
-- 清理 (无 FK), 生命周期 90d。
--
-- 前置: 无。回滚: DROP 两表 (行为数据可弃, 显式勾选在 settings.kv 不受影响)。

CREATE TABLE IF NOT EXISTS interest_signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id     TEXT NOT NULL,             -- hotspots.id (写入时归因, 无 FK)
    domain      TEXT NOT NULL,             -- 10 实践域之一 (写入时 classify_practice_domain)
    signal_type TEXT NOT NULL,             -- 'view'|'read'|'dwell'|'deep_read'|'favorite'
    weight      REAL NOT NULL,             -- 写入时按 PRD §1 权重表定死, 聚合免重算
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_interest_signals_time
    ON interest_signals(created_at);
CREATE INDEX IF NOT EXISTS idx_interest_signals_domain_time
    ON interest_signals(domain, created_at);
CREATE INDEX IF NOT EXISTS idx_interest_signals_item_type_time
    ON interest_signals(item_id, signal_type, created_at);

CREATE TABLE IF NOT EXISTS interest_domain_weights (
    domain            TEXT PRIMARY KEY,    -- 10 实践域之一
    explicit_selected INTEGER NOT NULL DEFAULT 0,   -- 显式勾选 (镜像 settings.kv, 聚合时刷新)
    behavioral_score  REAL NOT NULL DEFAULT 0.0,    -- B'(d) 归一化行为分 [0,1]
    blended_score     REAL NOT NULL DEFAULT 0.0,    -- S(d) 融合分
    events_30d        INTEGER NOT NULL DEFAULT 0,   -- 近 30 天信号数 (可解释/权重条)
    last_event_at     TEXT,
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
