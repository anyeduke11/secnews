"""Wiki MCP tools — v0.5 §18.4: llm-wiki-2.0 消费工具族。

替代传统 RAG retrieve: agent 通过这些端点消费文件系统知识库。
经 fastapi-mcp 自动暴露为 MCP tool (operation_id 注册见 mcp_config.py)。

- POST /api/wiki/search    wiki_search  — FTS5 全文搜 items/chunks
- GET  /api/wiki/read      wiki_read    — 读单个 .md 全文
- GET  /api/wiki/graph     wiki_graph   — 概念邻接 (graph.json BFS k=1)
- GET  /api/wiki/trace     db_trace     — 反查事件对应 (wiki_events)
- POST /api/wiki/write     wiki_write   — agent 持久产物写回 (经 ai_hub 单写路径)
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.logging_config import logger
from backend.repository.db import get_connection

router = APIRouter(prefix="/api/wiki", tags=["wiki-tools"])

# knowledge/ 根目录 (与 mcp_agent_tools.CONCEPT_DIR 同源逻辑, 可被测试覆盖)
KNOWLEDGE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "knowledge",
)

# 路径白名单校验: 只允许 [子目录/]名称.md, 禁止路径穿越 (P4-9 同款)
_PATH_RE = re.compile(r"^[a-z0-9][a-z0-9\-_/]*[a-z0-9_]\.md$")


# ---------------------------------------------------------------------------
# wiki_search — FTS5 全文搜索
# ---------------------------------------------------------------------------
class WikiSearchInput(BaseModel):
    """wiki_search — 全文搜索 llm-wiki-2.0。"""

    q: str = Field(..., min_length=1, description="查询关键词 (中英文均可)")
    limit: int = Field(20, ge=1, le=50, description="返回条数上限")


@router.post("/search")
async def wiki_search(req: WikiSearchInput):
    """FTS5 全文搜索知识条目 chunks (中文 trigram / ASCII unicode61 / LIKE 回退)。"""
    q = req.q.strip()
    conn = get_connection()
    sanitized = q.replace('"', '""')
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", q))
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
                (sanitized, req.limit),
            ).fetchall()
        except Exception as exc:
            logger.warning(f"wiki_search CJK FTS failed: {exc}")
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
                (sanitized, req.limit),
            ).fetchall()
        except Exception:
            rows = []
    if not rows:  # LIKE 回退 (短查询/无命中)
        like = f"%{q}%"
        rows = conn.execute(
            "SELECT item_id, chunk_index, substr(content, 1, 160) AS snippet "
            "FROM knowledge_chunks WHERE content LIKE ? OR summary LIKE ? LIMIT ?",
            (like, like, req.limit),
        ).fetchall()

    results = []
    for r in rows:
        d = dict(r)
        d["wiki_path"] = f"items/{d['item_id']}.md"
        results.append(d)
    return {"results": results, "total": len(results)}


# ---------------------------------------------------------------------------
# wiki_read — 读单个 .md 全文
# ---------------------------------------------------------------------------
@router.get("/read")
async def wiki_read(path: str = Query(..., min_length=1, description="相对 knowledge/ 的路径")):
    """读取 llm-wiki-2.0 单个 .md 文件全文 (含 frontmatter)。

    路径白名单校验, 只允许 items|concepts|learning|content|summaries 下
    的 .md 文件, 禁止路径穿越。
    """
    normalized = os.path.normpath(path).replace("\\", "/")
    if not _PATH_RE.fullmatch(normalized):
        raise HTTPException(status_code=400, detail="path 仅允许 小写字母/数字/-_/.md 组合")
    allowed_roots = ("items", "concepts", "learning", "content", "summaries")
    if not normalized.startswith(allowed_roots):
        raise HTTPException(status_code=400, detail=f"path 必须位于 {allowed_roots} 之下")

    full = os.path.join(KNOWLEDGE_DIR, normalized)
    # 双保险: resolve 后必须仍在 KNOWLEDGE_DIR 内
    if not os.path.realpath(full).startswith(os.path.realpath(KNOWLEDGE_DIR)):
        raise HTTPException(status_code=400, detail="路径穿越被拒绝")
    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="文件不存在")

    with open(full, encoding="utf-8") as f:
        content = f.read()
    return {"path": normalized, "content": content, "size": len(content)}


# ---------------------------------------------------------------------------
# wiki_graph — 概念邻接
# ---------------------------------------------------------------------------
@router.get("/graph")
async def wiki_graph(
    concept: str = Query(..., min_length=1, description="概念名 (小写连字符)"),
    depth: int = Query(1, ge=1, le=2, description="BFS 深度 (1-2)"),
):
    """从 concepts/graph.json 取概念邻接 (BFS k=depth)。

    graph.json 不存在或概念缺失时返回空邻接 (不报错, 方便 agent 探索)。
    """
    graph_file = os.path.join(KNOWLEDGE_DIR, "concepts", "graph.json")
    adjacency: dict[str, list[str]] = {}
    if os.path.isfile(graph_file):
        try:
            with open(graph_file, encoding="utf-8") as f:
                data = json.load(f)
            # 兼容两种形态: 直接邻接表 {"concept": [...]} 或 {"edges": [...]}
            if isinstance(data, dict) and "edges" in data and isinstance(data["edges"], list):
                for e in data["edges"]:
                    src, dst = e.get("source"), e.get("target")
                    if src and dst:
                        adjacency.setdefault(src, []).append(dst)
                        adjacency.setdefault(dst, []).append(src)
            elif isinstance(data, dict):
                adjacency = {
                    k: v for k, v in data.items() if isinstance(v, list)
                }
        except Exception as exc:
            logger.warning(f"wiki_graph: failed to load graph.json: {exc}")

    key = concept.strip().lower()
    seen = {key}
    frontier = [key] if key in adjacency else []
    result: dict[str, list[str]] = {}
    for _ in range(depth):
        nxt: list[str] = []
        for node in frontier:
            neighbors = [n for n in adjacency.get(node, []) if n not in seen]
            result[node] = adjacency.get(node, [])
            for n in neighbors:
                seen.add(n)
                nxt.append(n)
        frontier = nxt
        if not frontier:
            break
    return {"concept": key, "found": key in adjacency, "graph": result}


# ---------------------------------------------------------------------------
# db_trace — 反查事件对应
# ---------------------------------------------------------------------------
class DbTraceInput(BaseModel):
    """db_trace — 反查知识条目的事件来源。"""

    wiki_path: str = Field("", description="按知识文件路径反查 (如 items/a1b2c3.md)")
    db_table: str = Field("", description="按运营层表反查 (如 hotspots)")
    db_row_id: str = Field("", description="配合 db_table 使用")
    limit: int = Field(50, ge=1, le=200)


@router.post("/trace")
async def db_trace(req: DbTraceInput):
    """查 wiki_events 事件对应表 — 一条知识是由哪次采集/哪个 agent 产生的。"""
    from backend.repository.wiki_event_repo import wiki_event_repo

    if req.wiki_path:
        events = wiki_event_repo.trace_by_wiki_path(req.wiki_path, req.limit)
    elif req.db_table and req.db_row_id:
        events = wiki_event_repo.trace_by_db_ref(req.db_table, req.db_row_id, req.limit)
    else:
        raise HTTPException(
            status_code=400, detail="需要 wiki_path 或 (db_table + db_row_id)"
        )
    return {"events": events, "total": len(events)}


# ---------------------------------------------------------------------------
# wiki_write — agent 持久产物写回 (v0.5 §18.2 强约束 1: 唯一写路径)
# ---------------------------------------------------------------------------
class WikiWriteInput(BaseModel):
    """wiki_write — 新建/更新 knowledge item (md 真源 + SQLite 索引)。"""

    item_id: str = Field(..., min_length=1, max_length=120,
                         description="条目 ID (即文件名 stem)")
    title: str = Field(..., min_length=1, description="标题")
    content: str = Field("", description="Markdown 正文 (不含 frontmatter)")
    source: str = Field("mcp", description="来源标识")
    source_url: str = Field("", description="原文 URL (可选)")
    tags: list[str] = Field(default_factory=list, description="标签")


@router.post("/write")
async def wiki_write(req: WikiWriteInput):
    """agent 持久产物写回 llm-wiki-2.0 — 经 ai_hub 单一写路径。

    md 是真相源: 写 items/{item_id}.md 成功后同步 SQLite 索引,
    并在 wiki_events 留 kind=agent_write 痕 (db_trace 可反查)。
    """
    from backend.repository.knowledge_repo import knowledge_repo
    from backend.services import ai_hub

    # item_id 白名单校验 (同 _PATH_RE 字符集, 防穿越/防非法文件名)
    if not re.fullmatch(r"[a-z0-9][a-z0-9\-_]*", req.item_id):
        raise HTTPException(status_code=400, detail="item_id 仅允许 小写字母/数字/-_")

    now = datetime.now(timezone.utc).isoformat()
    item = {
        "id": req.item_id,
        "title": req.title,
        "source": req.source or "mcp",
        "source_url": req.source_url,
        "tags": req.tags,
        "lifecycle": "kl:raw",
        "ingested_at": existing.ingested_at if (existing := knowledge_repo.get_item(req.item_id)) is not None else now,
        "updated_at": now,
    }
    try:
        ai_hub.write_item(item, content=req.content, agent="mcp:wiki_write")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"md 写入失败: {exc}")

    # md 成功后同步 SQLite 索引 (失败不影响真相源, 下次 full_sync 补齐)
    sync_id = None
    try:
        import pathlib

        from backend.services.knowledge_sync import ITEMS_DIR, sync_item_to_db
        sync_id = sync_item_to_db(pathlib.Path(ITEMS_DIR) / f"{req.item_id}.md")
    except Exception as exc:
        logger.warning(f"wiki_write index sync deferred for {req.item_id}: {exc}")

    return {
        "wiki_path": f"items/{req.item_id}.md",
        "item_id": req.item_id,
        "synced": sync_id is not None,
    }
