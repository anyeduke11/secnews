"""复习卡 enrich 解析 (2026-09-21 设计稿 §3.2, 纯查询, 无写路径)。

按 ``entity_type`` 注册表把 sm2_reviews 行解析成可读卡片:

- ``hotspot``        → ``hotspots`` (title / url / category / summary→excerpt)
- ``knowledge_item`` → ``knowledge_items`` (title / source_url→url / domain;
  无摘要列, excerpt 置空)
- 未命中或行已删除   → 兜底返回原 entity_id, title=None (前端如实渲染裸 id)

**注册表只读这两张表**: 其余 entity_type (concept 等) 无源表可解析,
一律走兜底。knowledge_items 经 ``knowledge_items_table()`` 解析
(生产 ATTACH warm.db, 测试单库)。
"""
from __future__ import annotations

from backend.repository.db import get_connection, knowledge_items_table

# enrich 后附加的字段 (契约固定, 缺省 None)
_ENRICH_KEYS = ("title", "url", "category", "excerpt")
_CHUNK = 90  # SQLite 默认变量上限 999, 分批稳妥


def _fetch_hotspots(ids: list[str]) -> dict[str, dict]:
    conn = get_connection()
    out: dict[str, dict] = {}
    for i in range(0, len(ids), _CHUNK):
        batch = ids[i:i + _CHUNK]
        marks = ",".join("?" * len(batch))
        rows = conn.execute(
            f"SELECT id, title, url, category, summary FROM hotspots "
            f"WHERE id IN ({marks})",
            batch,
        ).fetchall()
        for r in rows:
            out[r["id"]] = {
                "title": r["title"],
                "url": r["url"],
                "category": r["category"],
                "excerpt": (r["summary"] or "").strip() or None,
            }
    return out


def _fetch_knowledge(ids: list[str]) -> dict[str, dict]:
    ktbl = knowledge_items_table()
    conn = get_connection()
    out: dict[str, dict] = {}
    for i in range(0, len(ids), _CHUNK):
        batch = ids[i:i + _CHUNK]
        marks = ",".join("?" * len(batch))
        rows = conn.execute(
            f"SELECT id, title, source_url, domain FROM {ktbl} "
            f"WHERE id IN ({marks})",
            batch,
        ).fetchall()
        for r in rows:
            out[r["id"]] = {
                "title": r["title"],
                "url": r["source_url"],
                "category": r["domain"],
                "excerpt": None,  # knowledge_items 无摘要列
            }
    return out


# entity_type → 源表查询器 (注册表: 新类型在这里登记)
_RESOLVERS = {
    "hotspot": _fetch_hotspots,
    "knowledge_item": _fetch_knowledge,
}


def enrich_rows(rows: list[dict]) -> list[dict]:
    """为复习行附加 title/url/category/excerpt (原字段全保留)。

    未注册的 entity_type 或源行已删除 → 四键置 None, 前端如实渲染裸 id。
    """
    # 按 type 收集 id, 每类一次批量查询 (避免 N+1)
    ids_by_type: dict[str, list[str]] = {}
    for row in rows:
        rtype = row.get("entity_type")
        if rtype in _RESOLVERS:
            ids_by_type.setdefault(rtype, []).append(row["entity_id"])

    resolved: dict[str, dict[str, dict]] = {}
    for rtype, ids in ids_by_type.items():
        found = _RESOLVERS[rtype](ids)
        resolved[rtype] = found

    out: list[dict] = []
    for row in rows:
        item = dict(row)
        hit = resolved.get(row.get("entity_type"), {}).get(row["entity_id"])
        for key in _ENRICH_KEYS:
            item[key] = hit[key] if hit else None
        out.append(item)
    return out


__all__ = ["enrich_rows"]
