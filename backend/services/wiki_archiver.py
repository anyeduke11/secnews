"""wiki_archiver — llm-wiki-2.0 30 天自动归档 (v0.5 M3.5 §18)。

职责 (SPEC §18.2):
- 从 SQLite 扫描 ``ingested_at < now - 30d`` **且** ``favorited != true`` 的条目
- 把 frontmatter + 正文原子写入 ``llm-wiki-2.0/items/{id}.md``
- 同时生成 ``llm-wiki-2.0/sources/{id}.md`` (抓取元数据快照)
- 在 ``retention.json`` 写入初始 entry (initial_score=1.0, current_score=1.0)
- 调 ``wiki_event_repo`` 留痕 (kind=agent_write, agent=job:wiki_archiver)

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


__all__ = ["archive_item", "archive_overdue_items", "_atomic_write_text"]