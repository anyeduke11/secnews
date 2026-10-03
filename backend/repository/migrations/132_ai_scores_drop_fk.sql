-- 132_ai_scores_drop_fk.sql — v0.8.6 P1-2a: ai_scores.hotspot_id 剥跨域 FK
--
-- 根因 (DEV-0268 生产实锤): T1 评分对象是 knowledge_items 的 id (kl-*),
-- 而 ai_scores.hotspot_id REFERENCES hotspots(id) ON DELETE CASCADE —
-- 连接级 foreign_keys=ON 下 kl-* 每插必炸 IntegrityError, 被 write_score
-- 的 except 吞成 warning → ai_scores 恒 0 行 (gateway.score 155+ 次成功
-- 全部无声丢失, 审计 G2/E3 的实际源头之一)。
--
-- 语义: 评分对象自 v0.5 起就是 "hotspot OR knowledge item id" 双域,
-- 与 hotspots(id) 的引用关系自 kl 管线引入即悬空 — 剥离无语义损失
-- (对齐 P0-7/E15 warm 悬空 FK 自愈同判例)。表当前 0 行, 重建零迁移成本。
--
-- 幂等: 表重建型迁移, 依赖迁移器 duplicate-table 容忍重放 (P0-4/S2 同款)。

CREATE TABLE IF NOT EXISTS ai_scores_new (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hotspot_id  TEXT NOT NULL,                                      -- hotspot id 或 kl-* item id (双域)
    score       REAL NOT NULL CHECK(score >= 0 AND score <= 10),
    reason      TEXT,
    scorer      TEXT,
    scored_at   TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO ai_scores_new (id, hotspot_id, score, reason, scorer, scored_at, created_at)
SELECT id, hotspot_id, score, reason, scorer, scored_at, created_at FROM ai_scores;

DROP TABLE ai_scores;
ALTER TABLE ai_scores_new RENAME TO ai_scores;

CREATE INDEX IF NOT EXISTS idx_ai_scores_hotspot ON ai_scores(hotspot_id, scored_at DESC);
