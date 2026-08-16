-- 061_v0.4_chunk_fts_cjk.sql: 中文全文检索支持 (v0.4.0 收尾)
--
-- 背景: knowledge_chunks_fts 用 unicode61 tokenizer, 中文按整串 CJK 连续
-- 字符作为一个 token, MATCH '安全' 无法命中 "网络安全漏洞" 等更长 token。
-- FTS5 trigram tokenizer 按 3-gram 切分, 天然支持 CJK 子串匹配。
-- 方案: 保留原 unicode61 表 (ASCII 查询), 新增 trigram 表供中文查询,
-- 由搜索 API 按查询内容路由; 触发器保持两表同步。
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts_cjk USING fts5(
    content,
    summary,
    content=knowledge_chunks,
    tokenize='trigram'
);

CREATE TRIGGER IF NOT EXISTS knowledge_chunks_cjk_ai AFTER INSERT ON knowledge_chunks BEGIN
    INSERT INTO knowledge_chunks_fts_cjk(rowid, content, summary)
    VALUES (new.id, new.content, new.summary);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_chunks_cjk_ad AFTER DELETE ON knowledge_chunks BEGIN
    INSERT INTO knowledge_chunks_fts_cjk(knowledge_chunks_fts_cjk, rowid, content, summary)
    VALUES ('delete', old.id, old.content, old.summary);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_chunks_cjk_au AFTER UPDATE ON knowledge_chunks BEGIN
    INSERT INTO knowledge_chunks_fts_cjk(knowledge_chunks_fts_cjk, rowid, content, summary)
    VALUES ('delete', old.id, old.content, old.summary);
    INSERT INTO knowledge_chunks_fts_cjk(rowid, content, summary)
    VALUES (new.id, new.content, new.summary);
END;

-- 存量同步: 把已生成的 chunks 灌入 trigram 表
INSERT INTO knowledge_chunks_fts_cjk(rowid, content, summary)
SELECT id, content, summary FROM knowledge_chunks;
