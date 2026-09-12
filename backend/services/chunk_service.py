"""chunk_service — 知识条目段落切分生成器 (v0.4.0 收尾落地)。

背景: knowledge_chunks / knowledge_chunks_fts 表自迁移 054 建成后 0 行 —
生成逻辑只存在于手动 API (POST /api/knowledge/chunks/generate/{id}), 无
调度触发、无存量回填, 全文检索从未有数据。本 service 抽取为可复用函数,
供 API + scheduler job 共同调用; FTS5 同步由 054 的触发器自动完成。

切分规则:
- 读取 knowledge/items/{id}.md, 剥离 YAML frontmatter
- 按双换行 (\n\n) 切段落, 计算 char_start/char_end 原文定位
- 段落超过 100 字符时生成截断摘要, 否则用全文
- 已存在 chunks 的条目跳过 (幂等, 返回 created=0)
"""
from __future__ import annotations

import logging
from pathlib import Path

from backend.repository.db import get_connection
from backend.repository.knowledge_repo import knowledge_repo
from backend.services import knowledge_sync as _ksync

log = logging.getLogger("hotspot.chunk_service")

# 动态引用 knowledge_sync.ITEMS_DIR — 测试 monkeypatch 该模块属性时,
# import 时绑定会拿到旧值 (此前 chunk_service.ITEMS_DIR 绑定导致 404)
def _items_dir() -> Path:
    return _ksync.ITEMS_DIR

# 正文过短 (< 此字符数) 的条目不切分 (空壳条目没有段落价值)
MIN_CONTENT_LEN = 40
# 单条 chunk 最大字符数 (超长段落再按句切, 避免超大 chunk)
MAX_CHUNK_LEN = 2000

import re as _re

_SENTENCE_RE = _re.compile(r"[^。！？；\n]*[。！？；\n]")


def _split_paragraphs(content: str) -> list[tuple[int, int, str]]:
    """按段落切分, 返回 [(char_start, char_end, text)] (保留原文定位)。

    先按双换行切; 超长段落 (> MAX_CHUNK_LEN) 再按句号/换行粗切, 避免单
    chunk 过大拖慢 FTS 查询与展示。
    """
    out: list[tuple[int, int, str]] = []
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    for para in paragraphs:
        if len(para) <= MAX_CHUNK_LEN:
            cs = content.find(para)
            if cs < 0:
                continue
            out.append((cs, cs + len(para), para))
            continue
        # 超长段落: 按句子边界切 (。！？；\n)
        start = 0
        for m in _SENTENCE_RE.finditer(para):
            seg = para[start:m.end()].strip()
            if seg and len(seg) >= 20:
                cs = content.find(seg)
                if cs >= 0:
                    out.append((cs, cs + len(seg), seg))
            start = m.end()
        tail = para[start:].strip()
        if tail and len(tail) >= 20:
            cs = content.find(tail)
            if cs >= 0:
                out.append((cs, cs + len(tail), tail))
    return out


def generate_chunks_for_item(item_id: str) -> dict:
    """为单个条目生成 chunks (幂等: 已有则跳过)。

    Returns: {"item_id", "created", "skipped", "reason"}
    """
    item = knowledge_repo.get_item(item_id)
    if item is None:
        return {"item_id": item_id, "created": 0, "skipped": True, "reason": "item_not_found"}

    conn = get_connection()
    existing = conn.execute(
        "SELECT COUNT(*) FROM knowledge_chunks WHERE item_id = ?", (item_id,)
    ).fetchone()[0]
    if existing > 0:
        return {"item_id": item_id, "created": 0, "skipped": True, "reason": "already_exists"}

    md_path = _items_dir() / f"{item_id}.md"
    if not md_path.exists():
        return {"item_id": item_id, "created": 0, "skipped": True, "reason": "no_md_file"}

    raw = md_path.read_text(encoding="utf-8")
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        content = parts[2].strip() if len(parts) >= 3 else ""
    else:
        content = raw.strip()

    if len(content) < MIN_CONTENT_LEN:
        return {"item_id": item_id, "created": 0, "skipped": True, "reason": "too_short"}

    segments = _split_paragraphs(content)
    if not segments:
        return {"item_id": item_id, "created": 0, "skipped": True, "reason": "no_paragraphs"}

    try:
        conn.execute("BEGIN")
        for idx, (cs, ce, text) in enumerate(segments):
            summary = (text[:100] + "...") if len(text) > 100 else text
            conn.execute(
                "INSERT INTO knowledge_chunks "
                "(item_id, chunk_index, content, char_start, char_end, summary) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (item_id, idx, text, cs, ce, summary),
            )
        conn.execute("COMMIT")
    except Exception as e:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        log.error(f"chunk insert failed for {item_id}: {e}")
        return {"item_id": item_id, "created": 0, "skipped": True, "reason": f"error: {e}"}

    log.info(f"chunk_service: {item_id} → {len(segments)} chunks")
    return {"item_id": item_id, "created": len(segments), "skipped": False, "reason": None}


# ---------------------------------------------------------------------------
# 只读查询 (Batch 2 D: api 层 SQL 下沉落点 — knowledge_chunks_api / wiki_tools)
# ---------------------------------------------------------------------------
_CHUNK_COLS = "id, item_id, chunk_index, content, char_start, char_end, summary"


def list_chunks(item_id: str, *, include_created_at: bool = True) -> list[dict]:
    """某条目全部 chunks, 按 chunk_index 升序.

    Args:
        item_id: 知识条目 id。
        include_created_at: GET 列表端点含 created_at; generate 后的兼容
            返回不含 (JSON 形状逐字保持, 故用开关区分两种列集)。
    """
    conn = get_connection()
    cols = _CHUNK_COLS + (", created_at" if include_created_at else "")
    rows = conn.execute(
        f"SELECT {cols} FROM knowledge_chunks WHERE item_id = ? ORDER BY chunk_index",
        (item_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def search_chunks(q: str) -> dict:
    """knowledge chunks FTS5 检索 (v0.4.0: 中文路由) — GET /api/knowledge/chunks/search.

    - 含中文且长度 ≥3 → trigram 表 (knowledge_chunks_fts_cjk), 支持 CJK 子串
    - 纯 ASCII → unicode61 表 (knowledge_chunks_fts)
    - FTS 无命中或 2 字短查询 → LIKE 回退 (chunks 规模小, LIKE 足够)

    Returns: ``{"results": [...], "total": n}``
    """
    conn = get_connection()
    sanitized = q.replace('"', '""')
    has_cjk = bool(_re.search(r"[\u4e00-\u9fff]", q))

    def _search_fts() -> list:
        if has_cjk and len(q) >= 3:
            # trigram 表 (FTS5 trigram 要求查询 ≥3 字符)
            try:
                return conn.execute(
                    """
                    SELECT c.item_id, c.chunk_index,
                           substr(c.content, 1, 120) AS content_snippet,
                           c.summary
                    FROM knowledge_chunks_fts_cjk
                    JOIN knowledge_chunks c ON knowledge_chunks_fts_cjk.rowid = c.id
                    WHERE knowledge_chunks_fts_cjk MATCH ?
                    ORDER BY rank
                    LIMIT 50
                    """,
                    (sanitized,),
                ).fetchall()
            except Exception as exc:
                log.warning("CJK FTS5 query failed: %s — %r", exc, q)
                return []
        # unicode61 (ASCII)
        try:
            return conn.execute(
                """
                SELECT c.item_id, c.chunk_index,
                       snippet(knowledge_chunks_fts, 0, '<b>', '</b>', '...', 64) AS content_snippet,
                       c.summary
                FROM knowledge_chunks_fts
                JOIN knowledge_chunks c ON knowledge_chunks_fts.rowid = c.id
                WHERE knowledge_chunks_fts MATCH ?
                ORDER BY rank
                LIMIT 50
                """,
                (sanitized,),
            ).fetchall()
        except Exception as exc:
            log.warning("FTS5 query failed: %s — query=%r", exc, q)
            return []

    rows = _search_fts()
    # 回退: FTS 无命中 (或 2 字短查询) → LIKE 全文模糊匹配
    if not rows:
        like = f"%{q}%"
        try:
            rows = conn.execute(
                "SELECT id AS item_id, chunk_index, "
                "substr(content, 1, 120) AS content_snippet, summary "
                "FROM knowledge_chunks "
                "WHERE content LIKE ? OR summary LIKE ? LIMIT 50",
                (like, like),
            ).fetchall()
        except Exception:
            rows = []

    results = [dict(r) for r in rows]
    return {"results": results, "total": len(results)}


def wiki_search_chunks(q: str, limit: int) -> list[dict]:
    """wiki_search 数据面 — FTS5 全文搜 chunks (llm-wiki-2.0 消费, /api/wiki/search).

    与 :func:`search_chunks` 的差异: snippet 截断 160 字符、无 summary 列、
    CJK <3 字符时仍先试 unicode61 表。返回原始行 dict 列表,
    wiki_path 由 api 层追加。
    """
    conn = get_connection()
    sanitized = q.replace('"', '""')
    has_cjk = bool(_re.search(r"[\u4e00-\u9fff]", q))
    rows: list = []

    if has_cjk and len(q) >= 3:
        try:
            rows = conn.execute(
                """
                SELECT c.item_id, c.chunk_index,
                       substr(c.content, 1, 160) AS snippet
                FROM knowledge_chunks_fts_cjk
                JOIN knowledge_chunks c ON knowledge_chunks_fts_cjk.rowid = c.id
                WHERE knowledge_chunks_fts_cjk MATCH ?
                ORDER BY rank LIMIT ?
                """,
                (sanitized, limit),
            ).fetchall()
        except Exception as exc:
            log.warning("wiki_search CJK FTS failed: %s", exc)
            rows = []
    if not rows:
        try:
            rows = conn.execute(
                """
                SELECT c.item_id, c.chunk_index,
                       snippet(knowledge_chunks_fts, 0, '<b>', '</b>', '...', 48) AS snippet
                FROM knowledge_chunks_fts
                JOIN knowledge_chunks c ON knowledge_chunks_fts.rowid = c.id
                WHERE knowledge_chunks_fts MATCH ?
                ORDER BY rank LIMIT ?
                """,
                (sanitized, limit),
            ).fetchall()
        except Exception:
            rows = []
    if not rows:  # LIKE 回退 (短查询/无命中)
        like = f"%{q}%"
        rows = conn.execute(
            "SELECT item_id, chunk_index, substr(content, 1, 160) AS snippet "
            "FROM knowledge_chunks WHERE content LIKE ? OR summary LIKE ? LIMIT ?",
            (like, like, limit),
        ).fetchall()
    return [dict(r) for r in rows]


__all__ = [
    "MIN_CONTENT_LEN",
    "generate_chunks_for_item",
    "list_chunks",
    "search_chunks",
    "wiki_search_chunks",
]
