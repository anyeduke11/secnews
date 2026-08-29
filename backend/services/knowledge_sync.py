"""Knowledge sync service — bidirectional sync between knowledge/ .md files and SQLite.

Truth model (P3 重构后统一约定)
---------------------------------
- ``items/`` 与 ``concepts/``: **md 文件是唯一真相源**, SQLite 是可随时从 md
  全量重建的只读索引。``full_sync_*`` 除 upsert 外还会清理 md 已删除的孤儿行;
  DB→md 回写 (``write_item_to_md``) 保留 md-only frontmatter 字段不丢失。
- ``content/drafts/``: SQLite 行是元数据真相源 (title/status/calendar_id),
  md 只存正文 (无 frontmatter) — 运行时状态不适合落盘 md。

Design notes
------------
- ``knowledge/`` lives at the project root (parent.parent.parent of this
  file: services/ → backend/ → project root).
- A minimal YAML frontmatter parser is used to avoid a ``pyyaml`` dependency.
  It handles the subset of YAML used by the ``_SCHEMA.md`` contract:
  scalar ``key: value`` pairs and ``- item`` lists. Quoted strings are
  stripped of surrounding ``"`` or ``'``.
- ``sync_item_to_db`` / ``sync_concept_to_db`` import the repository lazily
  so this module can be imported without a live DB connection (useful for
  the watchdog observer which may start before ``init_db`` runs).
- ``write_item_to_md`` preserves the markdown body below the frontmatter
  when writing back from SQLite.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

log = logging.getLogger("hotspot.knowledge_sync")

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge"
ITEMS_DIR = KNOWLEDGE_DIR / "items"
CONCEPTS_DIR = KNOWLEDGE_DIR / "concepts"
DRAFTS_DIR = KNOWLEDGE_DIR / "content" / "drafts"

# YAML frontmatter pattern: starts with ---, ends with ---
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# v0.5 §18: full_sync_* 批量重建索引时置 True — 同步事件不写 wiki_events
# (避免每次全量同步灌入数百行遥测噪音; watcher 单文件增量才是真实写事件)
_bulk_syncing = False


def _log_wiki_event(kind: str, wiki_path: str, db_table: str, db_row_id: str) -> None:
    """wiki_events 留痕 (migration 065 承诺的写入方之一)。失败静默降级。"""
    if _bulk_syncing:
        return
    try:
        from backend.repository.wiki_event_repo import wiki_event_repo

        wiki_event_repo.log(
            kind=kind, wiki_path=wiki_path, db_table=db_table, db_row_id=db_row_id,
            agent="watcher",
        )
    except Exception as e:
        log.debug(f"wiki_events log skipped for {wiki_path}: {e}")


def _coerce_scalar(value: str):
    """Coerce a YAML scalar string to int/float when it looks numeric.

    Keeps the original string if it is not a clean number (e.g. URLs,
    dates, or identifiers that happen to start with digits).
    """
    if not value:
        return value
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def parse_frontmatter(md_path: Path) -> dict | None:
    """Parse YAML frontmatter from a .md file.

    Returns dict of frontmatter fields, or None if no frontmatter found.
    """
    try:
        text = md_path.read_text(encoding="utf-8")
    except Exception:
        return None
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    # Simple YAML parsing (no pyyaml dependency)
    fm: dict = {}
    current_key: str | None = None
    current_list: list = []
    for line in m.group(1).split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" in stripped and not stripped.startswith("- "):
            if current_key is not None and current_list:
                fm[current_key] = current_list
                current_list = []
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if value == "null":
                value = None
            elif value == "true":
                value = True
            elif value == "false":
                value = False
            elif value.startswith("[") and value.endswith("]"):
                # Inline JSON array (e.g. sources: ["cubox"], tags: ["a","b"])
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    value = _coerce_scalar(value)
            else:
                # Try to coerce numeric scalars so downstream isinstance
                # checks (int/float) work — e.g. mastery: 50 → int 50.
                value = _coerce_scalar(value)
            current_key = key
            if value != "":
                fm[key] = value
                current_key = None
            else:
                current_list = []
        elif stripped.startswith("- ") and current_key is not None:
            current_list.append(stripped[2:].strip().strip('"').strip("'"))
    if current_key is not None and current_list:
        fm[current_key] = current_list
    return fm


def sync_item_to_db(md_path: Path) -> str | None:
    """Sync a single knowledge/items/{id}.md to SQLite. Returns item id (or None if skipped)."""
    fm = parse_frontmatter(md_path)
    if fm is None:
        return None

    from backend.domain.knowledge_models import KnowledgeItem, now_iso
    from backend.repository.knowledge_repo import knowledge_repo

    item_id = fm.get("id", md_path.stem)

    # P1-1: lifecycle 解析 — md 有 lifecycle 字段则用之; 没有则**保留 DB 现值**,
    # 不再回退 compiled/signal/generate (此前回退导致 watchdog full_sync 把
    # T1-T4 推进的 kl:* 状态批量抹回旧值, 状态机在"推进↔被抹除"间震荡)。
    # P1.5: 全新条目统一落 kl:raw (单轨化, 不再产生 legacy SAG 值)
    lifecycle = fm.get("lifecycle")
    if lifecycle is None:
        existing_row = knowledge_repo.get_item(item_id)
        if existing_row is not None and existing_row.lifecycle:
            lifecycle = existing_row.lifecycle
        else:
            # 全新条目 (DB 无记录): 统一 kl:raw
            lifecycle = "kl:raw"

    item = KnowledgeItem(
        id=item_id,
        title=fm.get("title", "Untitled"),
        source=fm.get("source", "unknown"),
        source_url=fm.get("source_url"),
        domain=fm.get("domain"),
        topic=fm.get("topic"),
        type=fm.get("type"),
        difficulty=fm.get("difficulty"),
        tags=fm.get("tags", []) if isinstance(fm.get("tags"), list) else [],
        concepts=fm.get("concepts", []) if isinstance(fm.get("concepts"), list) else [],
        mastery=fm.get("mastery", 0) if isinstance(fm.get("mastery"), (int, float)) else 0,
        lifecycle=lifecycle,
        news_type=fm.get("news_type") if isinstance(fm.get("news_type"), str) else None,
        tech_stack=fm.get("tech_stack", []) if isinstance(fm.get("tech_stack"), list) else [],
        ingested_at=fm.get("ingested_at", now_iso()),
        updated_at=now_iso(),
    )
    knowledge_repo.upsert_item(item)
    log.debug(f"synced item to db: {item.id}")
    _log_wiki_event("sync_item", f"items/{md_path.name}", "knowledge_items", item.id)
    return item.id


def sync_concept_to_db(md_path: Path) -> str | None:
    """Sync a single knowledge/concepts/{slug}.md to SQLite. Returns slug (or None if skipped)."""
    fm = parse_frontmatter(md_path)
    if fm is None:
        return None

    from backend.domain.knowledge_models import KnowledgeConcept, now_iso
    from backend.repository.knowledge_repo import knowledge_repo

    concept = KnowledgeConcept(
        slug=fm.get("slug", md_path.stem),
        title=fm.get("title", "Untitled"),
        domain=fm.get("domain"),
        source_items=fm.get("source_items", []) if isinstance(fm.get("source_items"), list) else [],
        local_wiki_ref=fm.get("local_wiki_ref"),
        updated_at=now_iso(),
    )
    knowledge_repo.upsert_concept(concept)
    log.debug(f"synced concept to db: {concept.slug}")
    _log_wiki_event("sync_concept", f"concepts/{md_path.name}", "knowledge_concepts", concept.slug)
    return concept.slug


def write_item_to_md(item: dict, content: str | None = None) -> None:
    """Write a knowledge item from SQLite back to knowledge/items/{id}.md.

    md 是真相源: 除保留正文外, 还保留 DB 中不存在的 md-only frontmatter
    字段 (sources/last_reviewed/review_count/related_items), 避免回写时
    静默重置为默认值。

    Args:
        item: knowledge_items dict
        content: Markdown 正文 (默认保留文件已有正文, 传 '' 表示清空)
    """
    item_id = item["id"]
    path = ITEMS_DIR / f"{item_id}.md"
    body = ""
    existing_fm: dict = {}
    if path.exists():
        existing_fm = parse_frontmatter(path) or {}
    if content is not None:
        # 调用方显式指定正文 (新建或覆盖)
        body = content
    elif path.exists():
        # 默认保留已有正文
        existing = path.read_text(encoding="utf-8")
        m = _FRONTMATTER_RE.match(existing)
        if m:
            body = existing[m.end():]

    # md-only 字段: DB 无对应列, 从现有 frontmatter 继承 (item dict 优先)
    last_reviewed = item.get("last_reviewed") or existing_fm.get("last_reviewed")
    review_count = item.get("review_count", existing_fm.get("review_count", 0))
    related_items = item.get("related_items") or existing_fm.get("related_items") or []
    sources = item.get("sources") or existing_fm.get("sources")
    sources_line = f"sources: {json.dumps(sources, ensure_ascii=False)}\n" if sources else ""

    frontmatter = f"""---
id: "{item.get('id', item_id)}"
title: "{item.get('title', 'Untitled')}"
source: "{item.get('source', 'unknown')}"
source_url: "{item.get('source_url', '')}"
ingested_at: "{item.get('ingested_at', '')}"
lifecycle: "{item.get('lifecycle', 'kl:raw')}"
news_type: "{item.get('news_type', '')}"
tech_stack: {json.dumps(item.get('tech_stack', []), ensure_ascii=False)}
domain: {item.get('domain') or 'null'}
topic: {item.get('topic') or 'null'}
type: {item.get('type') or 'null'}
difficulty: {item.get('difficulty') or 'null'}
tags: {json.dumps(item.get('tags', []), ensure_ascii=False)}
concepts: {json.dumps(item.get('concepts', []), ensure_ascii=False)}
mastery: {item.get('mastery', 0)}
last_reviewed: {last_reviewed or 'null'}
review_count: {review_count}
related_items: {json.dumps(related_items, ensure_ascii=False)}
{sources_line}---

"""
    ITEMS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(frontmatter + body, encoding="utf-8")


def update_md_frontmatter_field(md_path: Path, key: str, value: str) -> bool:
    """就地更新单个 frontmatter 字段 (保留其余内容不变)。

    md 是真相源: DB 直改字段 (如 concept.local_wiki_ref) 必须同步回写 md,
    否则下次 full_sync 会用旧 frontmatter 值回滚 DB。

    Returns True on success, False if file missing / no frontmatter / write failed.
    """
    try:
        text = md_path.read_text(encoding="utf-8")
    except Exception:
        return False
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return False
    fm_block = m.group(1)
    new_line = f'{key}: "{value}"'
    key_re = re.compile(rf"^{re.escape(key)}:.*$", re.MULTILINE)
    if key_re.search(fm_block):
        new_block = key_re.sub(lambda _m: new_line, fm_block, count=1)
    else:
        new_block = fm_block + "\n" + new_line
    new_text = f"---\n{new_block}\n---\n" + text[m.end():]
    try:
        md_path.write_text(new_text, encoding="utf-8")
        return True
    except Exception as e:
        log.error(f"update_md_frontmatter_field failed for {md_path}: {e}")
        return False


def full_sync_items_to_db() -> int:
    """Sync all knowledge/items/*.md to SQLite. Returns count.

    md 是真相源: 同步后清理 DB 中 md 已不存在的孤儿行 (仅当目录非空,
    避免目录意外为空时清空索引)。
    """
    if not ITEMS_DIR.exists():
        return 0
    from backend.repository.knowledge_repo import knowledge_repo

    global _bulk_syncing
    _bulk_syncing = True
    count = 0
    seen: set[str] = set()
    for f in ITEMS_DIR.glob("*.md"):
        item_id = sync_item_to_db(f)
        # 无 frontmatter 的文件不入库, 但 stem 仍计入保留集 (不误删)
        seen.add(item_id or f.stem)
        count += 1
    _bulk_syncing = False
    if count > 0:
        orphans = [i for i in knowledge_repo.list_item_ids() if i not in seen]
        for orphan_id in orphans:
            knowledge_repo.delete_item(orphan_id)
        if orphans:
            log.info(f"full sync: removed {len(orphans)} orphan item rows")
    log.info(f"full sync: {count} items")
    return count


def full_sync_concepts_to_db() -> int:
    """Sync all knowledge/concepts/*.md to SQLite. Returns count.

    md 是真相源: 同步后清理孤儿行 (同 full_sync_items_to_db)。
    """
    if not CONCEPTS_DIR.exists():
        return 0
    from backend.repository.knowledge_repo import knowledge_repo

    global _bulk_syncing
    _bulk_syncing = True
    count = 0
    seen: set[str] = set()
    for f in CONCEPTS_DIR.glob("*.md"):
        slug = sync_concept_to_db(f)
        seen.add(slug or f.stem)
        count += 1
    _bulk_syncing = False
    if count > 0:
        orphans = [s for s in knowledge_repo.list_concept_slugs() if s not in seen]
        for orphan_slug in orphans:
            knowledge_repo.delete_concept(orphan_slug)
        if orphans:
            log.info(f"full sync: removed {len(orphans)} orphan concept rows")
    log.info(f"full sync: {count} concepts")
    return count


def sync_draft_to_db(md_path: Path) -> None:
    """Sync a single knowledge/content/drafts/*.md to SQLite.

    Drafts .md files do NOT have frontmatter — the SQLite row is the
    metadata source of truth (id/title/status/calendar_id). This function
    reconciles the filesystem with SQLite:
    - If the .md file exists but has no SQLite row, create one (title from
      the first ``# heading`` line, or the filename stem).
    - If the .md file was deleted but a SQLite row points to it, log a
      warning (the row is left untouched — deletion is handled by the
      content_service API, not by the watcher).
    """
    from backend.domain.knowledge_models import now_iso
    from backend.repository.knowledge_repo import knowledge_repo

    # file_path convention matches content_service._draft_rel_path:
    # "knowledge/content/drafts/{name}.md" (relative to project root)
    rel_path = f"knowledge/content/drafts/{md_path.name}"
    rows = knowledge_repo.list_drafts()
    match = next((r for r in rows if r["file_path"] == rel_path), None)
    if match is not None:
        # SQLite already tracks this draft — nothing to sync (drafts .md
        # has no frontmatter, so the filesystem holds only the body).
        return

    # No SQLite row — create one. Extract title from first # heading.
    title = md_path.stem  # fallback: filename
    try:
        text = md_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("# "):
                title = line[2:].strip()
                break
    except Exception:
        pass

    now = now_iso()
    draft = {
        "file_path": rel_path,
        "title": title,
        "status": "draft",
        "calendar_id": None,
        "created_at": now,
        "updated_at": now,
    }
    knowledge_repo.upsert_draft(draft)
    log.info(f"synced draft from filesystem: {rel_path} (title={title!r})")


def full_sync_drafts_to_db() -> int:
    """Sync all knowledge/content/drafts/*.md to SQLite. Returns count.

    For each .md file in drafts/, ensure a SQLite row exists. Drafts .md
    files have no frontmatter — the body is the article content and the
    title is derived from the first ``# heading`` line.
    """
    if not DRAFTS_DIR.exists():
        return 0
    count = 0
    for f in DRAFTS_DIR.glob("*.md"):
        sync_draft_to_db(f)
        count += 1
    log.info(f"full sync: {count} drafts")
    return count


def backfill_lifecycle_to_md() -> dict:
    """P1-1: 为缺少 lifecycle 字段的 items/*.md 补写 DB 当前值 (保守回填).

    背景: 历史导入器 (bookmark/cubox) 自写 frontmatter 模板不含 lifecycle,
    而 DB 已被 T1-T4 推进到 kl:* 状态 → 文件真相源与 DB 状态分离, 且任何
    full_sync 会把 DB 抹回旧值。本函数仅对**缺少 lifecycle 键**的文件,
    在 frontmatter 中插入一行 lifecycle 值 (来自 DB, 缺省 'signal'),
    不重写正文、不改动其他字段。

    Returns: {"scanned": N, "added": M, "skipped_kl": K}
    """
    from backend.repository.knowledge_repo import knowledge_repo

    added = 0
    skipped_kl = 0
    scanned = 0
    if not ITEMS_DIR.exists():
        return {"scanned": 0, "added": 0, "skipped_kl": 0}

    for f in sorted(ITEMS_DIR.glob("*.md")):
        scanned += 1
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        # 已有 lifecycle 键 → 跳过
        m = _FRONTMATTER_RE.match(text)
        if not m:
            continue
        fm_block = m.group(1)
        if re.search(r"(?m)^lifecycle\s*:", fm_block):
            continue
        # 从 DB 取当前 lifecycle (P1-3: 缺省 kl:raw)
        item_id = f.stem
        lifecycle = "kl:raw"
        try:
            row = knowledge_repo.get_item(item_id)
            if row is not None and row.lifecycle:
                lifecycle = row.lifecycle
        except Exception:
            pass
        # 在 frontmatter 中找 `compiled:` 行, 在其前插入 lifecycle 行
        lines = fm_block.splitlines()
        insert_at = 0
        for i, line in enumerate(lines):
            if line.strip().startswith("compiled:"):
                insert_at = i
                break
        lines.insert(insert_at, f'lifecycle: "{lifecycle}"')
        new_fm = "\n".join(lines)
        # 替换原 frontmatter 块 (保留其余结构)
        new_text = _FRONTMATTER_RE.sub(
            lambda _m, _fm=new_fm: "---\n" + _fm + "\n---", text, count=1
        )
        f.write_text(new_text, encoding="utf-8")
        if lifecycle.startswith("kl:"):
            skipped_kl = skipped_kl + 1  # 本就从 kl 状态回填
        added += 1

    log.info(
        f"backfill_lifecycle_to_md: scanned={scanned} added={added} "
        f"(kl-valued={skipped_kl})"
    )
    return {"scanned": scanned, "added": added, "skipped_kl": skipped_kl}
