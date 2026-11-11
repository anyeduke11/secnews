"""wiki_archiver — llm-wiki-2.0 30 天自动归档 (v0.5 M3.5 §18)。

职责 (SPEC §18.2):
- 从 SQLite 扫描 ``ingested_at < now - 30d`` **且** ``favorited != true`` 的条目
- 把 frontmatter + 正文原子写入 ``llm-wiki-2.0/items/{id}.md``
- 同时生成 ``llm-wiki-2.0/sources/{id}.md`` (抓取元数据快照)
- 在 ``retention.json`` 写入初始 entry (initial_score=1.0, current_score=1.0)
- 调 ``wiki_event_repo`` 留痕 (kind=agent_write, agent=job:wiki_archiver)

v0.8.8 R-17 追加职责: ``sink_hotspots_to_feed()`` 把 ``hotspots`` 同口径
(30 天外 + 未收藏) 沉降到 ``feed/{yyyy-mm}.md``, 留痕 kind=sink。
当前为**只写阶段** — 不删 DB 行, 删行待 C2.4 重建管道通过 T4 验收后开启。

关闭策略: ``config.llm_wiki_v2=False`` 时整个模块返回空集 (上层 job 直接跳过)。

设计边界:
- **不删 SQLite 行** — SQLite 只是索引, 真源是 .md。归档后 SQLite 仍可读,
  但 admin 可手动 truncate archived 段 (M5 决策, 不在本模块范围)
- **幂等** — 重复调用同一条目, 检测 ``llm-wiki-2.0/items/{id}.md`` 已存在则 skip
- **atomic** — 先写 ``.tmp``, 再 ``os.replace`` (Linux/Mac atomic rename)
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("hotspot.wiki_archiver")


# ---------------------------------------------------------------------------
# 原子写 + retention 读改写 (纯函数, 易测)
# ---------------------------------------------------------------------------

def _atomic_write_text(target: Path, content: str) -> None:
    """原子写文本文件: 写 .tmp 后 rename, 防止半截文件。

    Args:
        target: 目标 .md 路径
        content: 完整文件内容
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)


def _atomic_write_json(target: Path, obj: dict) -> None:
    """原子写 JSON 文件 (indent=2, ensure_ascii=False 便于 git diff)。"""
    _atomic_write_text(target, json.dumps(obj, indent=2, ensure_ascii=False))


def _load_retention(retention_path: Path) -> dict:
    """读 retention.json, 缺失/损坏时返回空骨架。"""
    if not retention_path.exists():
        return {"$schema_version": "0.5.0", "entries": []}
    try:
        return json.loads(retention_path.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"retention.json unreadable, returning empty: {e}")
        return {"$schema_version": "0.5.0", "entries": []}


def _ensure_retention_entry(
    retention_path: Path, item_id: str, now: str | None = None
) -> bool:
    """确保 retention.json 含 item_id entry; 已有则 skip。返回 True=新写入, False=已存在。

    initial_score / current_score 默认 1.0; last_accessed = now (ISO8601 UTC)。
    """
    obj = _load_retention(retention_path)
    for e in obj.get("entries", []):
        if e.get("id") == item_id:
            return False
    obj.setdefault("entries", []).append({
        "id": item_id,
        "initial_score": 1.0,
        "current_score": 1.0,
        "last_accessed": now or datetime.now(tz=timezone.utc).isoformat(),
        "decay_events": [],
    })
    _atomic_write_json(retention_path, obj)
    return True


# ---------------------------------------------------------------------------
# 单条目归档 (纯函数, 接收已构造的 dict; 不直连 DB, 由 job 层注入)
# ---------------------------------------------------------------------------

def archive_item(
    item: dict[str, Any],
    *,
    wiki_root: Path,
    body: str | None = None,
    source_meta: dict[str, Any] | None = None,
) -> Path:
    """归档单条 item 到 ``{wiki_root}/items/{id}.md``。

    Args:
        item: knowledge_items 行 dict (须含 id / title / ingested_at)
        wiki_root: llm-wiki-2.0 根目录
        body: Markdown 正文 (None=仅写 frontmatter, 常见于 stub 条目)
        source_meta: 抓取元数据 (parser / quality_gates / url / headers),
            None 时跳过 sources/{id}.md 写入

    Returns:
        写入的 items/{id}.md 路径
    """
    item_id = str(item.get("id", ""))
    if not item_id:
        raise ValueError("archive_item: item['id'] is required")

    items_dir = wiki_root / "items"
    target = items_dir / f"{item_id}.md"

    # 幂等: 已存在则直接返回
    if target.exists():
        log.debug(f"archive_item: {target} already exists, skip")
        return target

    # DEV-0241: 归档终态语义 — md 强制写 kl:archived (覆盖行上历史值),
    # 使"归档兜底物化"与"T4 发布门产出的真实知识"(kl:publish) 可区分。
    # md 先写 (真相源), DB 行随后同步更新 (watcher 也会按 md 值对齐, 双保险)。
    item = {**item, "lifecycle": "kl:archived"}

    # frontmatter 序列化为 YAML 子集 (scalar key: value + list)
    fm_lines = ["---"]
    for k, v in item.items():
        if k == "body":
            continue
        if isinstance(v, list):
            fm_lines.append(f"{k}:")
            for item_v in v:
                fm_lines.append(f"  - {_yaml_scalar(item_v)}")
        else:
            fm_lines.append(f"{k}: {_yaml_scalar(v)}")
    fm_lines.append("---")
    fm_text = "\n".join(fm_lines) + "\n"

    body_text = body if body is not None else ""
    full_text = fm_text + ("\n" + body_text if body_text else "")

    _atomic_write_text(target, full_text)

    # sources/{id}.md 可选元数据快照
    if source_meta:
        sources_dir = wiki_root / "sources"
        source_target = sources_dir / f"{item_id}.md"
        if not source_target.exists():
            sm_lines = ["---"]
            sm_lines.append(f"id: {item_id}")
            sm_lines.append(f"url: {source_meta.get('url', '')}")
            sm_lines.append(f"parser: {source_meta.get('parser', '')}")
            gates = source_meta.get("quality_gates", [])
            sm_lines.append("quality_gates:")
            for g in gates:
                sm_lines.append(f"  - {g}")
            sm_lines.append(
                f"fetched_at: {source_meta.get('fetched_at', datetime.now(tz=timezone.utc).isoformat())}"
            )
            sm_lines.append("---")
            _atomic_write_text(source_target, "\n".join(sm_lines) + "\n")

    # retention entry
    _ensure_retention_entry(wiki_root / "retention.json", item_id)

    # wiki_events 留痕 (失败静默降级, 不阻塞归档)
    try:
        from backend.repository.wiki_event_repo import wiki_event_repo

        wiki_event_repo.log(
            kind="agent_write",
            wiki_path=f"items/{item_id}.md",
            db_table="knowledge_items",
            db_row_id=item_id,
            agent="job:wiki_archiver",
        )
    except Exception as e:
        log.debug(f"wiki_events log skipped for items/{item_id}.md: {e}")

    # DB 行 lifecycle 对齐 kl:archived (与 md 同值; 失败不阻塞归档 —
    # watcher 下次同步 md 时会按 md 值对齐)
    try:
        from datetime import datetime as _dt

        from backend.repository.db import get_connection, knowledge_items_table

        get_connection().execute(
            f"UPDATE {knowledge_items_table()} SET lifecycle = 'kl:archived', "
            f"updated_at = ? WHERE id = ?",
            (_dt.now(tz=timezone.utc).isoformat(), item_id),
        )
    except Exception as e:
        log.debug(f"DB lifecycle update skipped for {item_id}: {e}")

    return target


def _yaml_scalar(v: Any) -> str:
    """最小化 YAML 标量序列化: 字符串加引号, 数字/布尔原样。"""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    # 包含特殊字符或空字符串时用双引号包
    if not s or any(c in s for c in ":#\n'\"[]{}"):
        return f'"{s.replace(chr(34), chr(92) + chr(34))}"'
    return s


# ---------------------------------------------------------------------------
# Job 入口 (调度器调用; 内部直连 SQLite)
# ---------------------------------------------------------------------------

def archive_overdue_items(
    *,
    wiki_root: Path,
    days: int = 30,
    dry_run: bool = False,
) -> dict[str, int]:
    """扫描 SQLite 知识条目, 归档 ``ingested_at < now - days`` 且未收藏的条目。

    Args:
        wiki_root: llm-wiki-2.0 根目录
        days: 归档阈值天数 (默认 30)
        dry_run: True 时只统计不写文件

    Returns:
        统计 dict: {scanned, archived, skipped, favorited, errors}
    """
    from datetime import timedelta

    from backend.repository.knowledge_repo import knowledge_repo

    stats = {"scanned": 0, "archived": 0, "skipped": 0, "favorited": 0, "errors": 0}
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)

    # 列出现有过期候选 (限 500/批, 防止单次 job 失控)
    try:
        candidates = knowledge_repo.list_archived_candidates(
            cutoff_iso=cutoff.isoformat(), limit=500
        )
    except Exception as e:
        log.error(f"wiki_archiver: list_archived_candidates failed: {e}")
        stats["errors"] += 1
        return stats

    for row in candidates:
        stats["scanned"] += 1
        item_id = str(row.get("id", ""))
        if not item_id:
            stats["errors"] += 1
            continue
        if row.get("favorited"):
            stats["favorited"] += 1
            continue
        # 幂等: 已存在则 skip
        target = wiki_root / "items" / f"{item_id}.md"
        if target.exists():
            stats["skipped"] += 1
            continue
        if dry_run:
            stats["archived"] += 1
            continue
        try:
            archive_item(row, wiki_root=wiki_root)
            stats["archived"] += 1
        except Exception as e:
            log.warning(f"archive_item failed for {item_id}: {e}")
            stats["errors"] += 1

    return stats


# ---------------------------------------------------------------------------
# v0.8.8 R-17 冷层沉降 (C2.3 只写阶段: hot → cold feed/, **不删 DB 行**)
# ---------------------------------------------------------------------------

# feed md 契约: 每条 hotspot 一行, 行内 JSON 由 HTML 注释包裹 —
# 机器可逆解析, 且 md 预览器/编辑器会忽略注释, 不影响可读性。
FEED_RECORD_MARKER = "<!--hsc:"
FEED_SCHEMA_VERSION = 1


def _feed_month(iso_ts: str) -> str:
    """ISO 时间串 → ``yyyy-mm`` 分月键 (解析失败回退 UTC 当月)。"""
    try:
        return datetime.fromisoformat(iso_ts).strftime("%Y-%m")
    except (TypeError, ValueError):
        return datetime.now(tz=timezone.utc).strftime("%Y-%m")


def _json_list(raw: Any) -> list:
    """``hotspots.tags`` / ``quality_flags`` 等 JSON 数组列 → list (坏值 → [])。"""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _feed_record(row: Any, tag_links: list[dict]) -> dict:
    """hotspots 行 → feed 记录 (逐列保真, 供 C2.4 重建还原整行)。"""
    return {
        "v": FEED_SCHEMA_VERSION,
        "id": row["id"],
        "title": row["title"],
        "summary": row["summary"] or "",
        "source": row["source"],
        "url": row["url"],
        "category": row["category"],
        "published_at": row["published_at"],
        "score": row["score"],
        "fetched_at": row["fetched_at"],
        "ingested_at": row["ingested_at"],
        "is_fallback": int(row["is_fallback"] or 0),
        "quality_score": row["quality_score"],
        "quality_flags": _json_list(row["quality_flags"]),
        "quality_checked_at": row["quality_checked_at"],
        "url_check_status": row["url_check_status"],
        "lifecycle": row["lifecycle"],
        "is_hidden": int(row["is_hidden"] or 0),
        "pick_score": row["pick_score"],
        "last_read_at": row["last_read_at"],
        "tags": _json_list(row["tags"]),
        "tag_links": tag_links,
    }


def _parse_feed_records(text: str) -> list[dict]:
    """从 feed md 解析全部记录 (坏行跳过, 不抛)。"""
    records: list[dict] = []
    for line in text.splitlines():
        s = line.strip()
        if not (s.startswith(FEED_RECORD_MARKER) and s.endswith("-->")):
            continue
        try:
            rec = json.loads(s[len(FEED_RECORD_MARKER) : -3])
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict) and rec.get("id"):
            records.append(rec)
    return records


def _render_feed_doc(month: str, records: list[dict]) -> str:
    """渲染 ``feed/{yyyy-mm}.md`` 全文 (frontmatter + 逐行记录)。"""
    head = [
        "---",
        "doc: feed",
        f"schema: {FEED_SCHEMA_VERSION}",
        f"month: {month}",
        f"records: {len(records)}",
        f"updated_at: {datetime.now(tz=timezone.utc).isoformat()}",
        "---",
        "",
    ]
    body = [
        f"{FEED_RECORD_MARKER}{json.dumps(r, ensure_ascii=False, sort_keys=True)}-->"
        for r in records
    ]
    return "\n".join(head + body) + "\n"


def _load_tag_links(conn: Any, hotspot_ids: list[str]) -> dict[str, list[dict]]:
    """批量取 ``hotspot_tags`` + ``tags.label``, 按 hotspot_id 分组。"""
    if not hotspot_ids:
        return {}
    placeholders = ",".join("?" * len(hotspot_ids))
    rows = conn.execute(
        f"""
        SELECT ht.hotspot_id, ht.tag_id, ht.confidence, t.label
        FROM hotspot_tags ht
        LEFT JOIN tags t ON t.id = ht.tag_id
        WHERE ht.hotspot_id IN ({placeholders})
        """,
        hotspot_ids,
    ).fetchall()
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["hotspot_id"], []).append(
            {
                "tag_id": r["tag_id"],
                "label": r["label"] or "",
                "confidence": r["confidence"],
            }
        )
    return out


def _select_sink_candidates(cutoff_iso: str, limit: int) -> list[Any]:
    """选批: 30 天外 + 未收藏 + 尚未沉降 (无 ``kind='sink'`` 事件)。"""
    from backend.repository.db import get_connection

    return (
        get_connection()
        .execute(
            """
            SELECT h.* FROM hotspots h
            WHERE COALESCE(h.ingested_at, h.fetched_at) < ?
              AND NOT EXISTS (
                  SELECT 1 FROM favorites f WHERE f.hotspot_id = h.id
              )
              AND NOT EXISTS (
                  SELECT 1 FROM wiki_events w
                  WHERE w.kind = 'sink' AND w.db_table = 'hotspots'
                    AND w.db_row_id = h.id
              )
            ORDER BY COALESCE(h.ingested_at, h.fetched_at) ASC
            LIMIT ?
            """,
            (cutoff_iso, limit),
        )
        .fetchall()
    )


def sink_hotspots_to_feed(
    *,
    wiki_root: Path,
    days: int = 30,
    limit: int = 500,
    dry_run: bool = False,
) -> dict[str, int]:
    """C2.3 只写阶段: 把 30 天外未收藏热点沉降到 ``feed/{yyyy-mm}.md``。

    本阶段**不删除** ``hotspots`` 行 —— 删行必须等 C2.4 重建管道上线并通过
    「删库 → 重建 → 行数一致」验收后开启 (RA-14: 重建能力是取消备份的前提)。

    写的顺序遵循「先写 md, 再回读校验, 最后记账」: 回读缺记录时本批不计账
    (下一轮 job 会重试), 并计入 ``errors`` 让 job 标记失败 (fail-loud)。

    Args:
        wiki_root: llm-wiki-2.0 根目录
        days: 沉降阈值天数 (默认 30)
        limit: 单批上限 (默认 500)
        dry_run: True 时只统计不写盘

    Returns:
        {selected, sunk, skipped, errors, months}
    """
    from datetime import timedelta

    from backend.repository.db import get_connection
    from backend.repository.wiki_event_repo import wiki_event_repo

    stats = {"selected": 0, "sunk": 0, "skipped": 0, "errors": 0, "months": 0}
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    rows = _select_sink_candidates(cutoff.isoformat(), limit)
    stats["selected"] = len(rows)
    if not rows or dry_run:
        return stats

    conn = get_connection()
    tag_links = _load_tag_links(conn, [r["id"] for r in rows])
    # 已记账 id 集合: 账不留洞 (md 已写但事件写失败的行, 下一轮补账)
    logged = {
        str(r["db_row_id"])
        for r in conn.execute(
            "SELECT db_row_id FROM wiki_events "
            "WHERE kind = 'sink' AND db_table = 'hotspots'"
        ).fetchall()
    }

    by_month: dict[str, list[dict]] = {}
    for row in rows:
        rec = _feed_record(row, tag_links.get(row["id"], []))
        key = _feed_month(str(rec["ingested_at"] or rec["fetched_at"]))
        by_month.setdefault(key, []).append(rec)

    for month, recs in by_month.items():
        path = wiki_root / "feed" / f"{month}.md"
        existing = (
            _parse_feed_records(path.read_text(encoding="utf-8"))
            if path.exists()
            else []
        )
        known = {str(r.get("id")) for r in existing}
        fresh = [r for r in recs if str(r["id"]) not in known]
        stats["skipped"] += len(recs) - len(fresh)

        if fresh:
            _atomic_write_text(path, _render_feed_doc(month, existing + fresh))
            readback = {
                str(r.get("id"))
                for r in _parse_feed_records(path.read_text(encoding="utf-8"))
            }
            missing = [r for r in fresh if str(r["id"]) not in readback]
            if missing:
                stats["errors"] += len(missing)
                log.error(
                    f"feed readback mismatch {path}: {len(missing)} record(s) missing, "
                    "batch not logged"
                )
                continue

        for rec in recs:
            rec_id = str(rec["id"])
            if rec_id in logged:
                continue
            try:
                wiki_event_repo.log(
                    kind="sink",
                    wiki_path=f"feed/{month}.md",
                    db_table="hotspots",
                    db_row_id=rec_id,
                    agent="job:wiki_archiver",
                    payload={"month": month, "schema": FEED_SCHEMA_VERSION},
                )
                logged.add(rec_id)
            except Exception as e:
                stats["errors"] += 1
                log.warning(f"wiki_events sink log failed for {rec_id}: {e}")

        stats["sunk"] += len(fresh)
        if fresh:
            stats["months"] += 1

    return stats


__all__ = [
    "_atomic_write_text",
    "archive_item",
    "archive_overdue_items",
    "sink_hotspots_to_feed",
]