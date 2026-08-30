-- 078: 修复 hotspots_fts 的 contentless 'delete' 触发器缺陷 (v0.6.3 P3-1 发现)。
--
-- 缺陷: 001_init.sql 建的 hotspots_ad / hotspots_au 在 'delete' 命令里只提供
-- rowid。contentless FTS5 的 'delete' 必须**同时提供旧词条值**才能移除倒排
-- 记录 — 只给 rowid 不报错但词条静默残留 (SQLite 3.53 实证), UPDATE/DELETE
-- 后旧 title/summary 词条残留会造成搜索假阳性。当前 hotspots 以 INSERT-only
-- + flag 更新为主故未爆发, 但机制是坏的 (任何内容级 UPDATE 都会触发)。
--
-- 修复: 用 "提供旧值" 的写法重建两个触发器; 并以 contentless 唯一允许的
-- 'delete-all' + 全量重灌清掉历史残留词条 (4.5k 行亚秒级, 一次性成本)。
-- hotspots_ai (INSERT 路径) 本就正确, 不动。

DROP TRIGGER IF EXISTS hotspots_ad;
CREATE TRIGGER hotspots_ad AFTER DELETE ON hotspots BEGIN
    INSERT INTO hotspots_fts(hotspots_fts, rowid, title, summary)
        VALUES ('delete', old.rowid, old.title, IFNULL(old.summary, ''));
END;

DROP TRIGGER IF EXISTS hotspots_au;
CREATE TRIGGER hotspots_au AFTER UPDATE ON hotspots BEGIN
    INSERT INTO hotspots_fts(hotspots_fts, rowid, title, summary)
        VALUES ('delete', old.rowid, old.title, IFNULL(old.summary, ''));
    INSERT INTO hotspots_fts(rowid, title, summary)
        VALUES (new.rowid, new.title, IFNULL(new.summary, ''));
END;

-- 清历史残留: 'delete-all' 是 contentless 表唯一允许的批量清空命令。
INSERT INTO hotspots_fts(hotspots_fts) VALUES ('delete-all');
INSERT INTO hotspots_fts(rowid, title, summary)
    SELECT rowid, title, IFNULL(summary, '') FROM hotspots;
