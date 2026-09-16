"""Cubox sync service — sync cubox cards to llm-wiki-2.0/items/*.md.

v0.6.3 P3-4: 路径全部走 wiki_fs/paths, 旧 ``knowledge/`` 根下线。
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

from backend.domain.knowledge_models import KnowledgeItem, now_iso
from backend.services.data_cleaning import find_similar_items, item_id_from_url
from backend.wiki_fs.paths import ITEMS_DIR

log = logging.getLogger("hotspot.cubox_sync")


def _cubox_env() -> dict[str, str]:
    """子进程环境: PATH 注入 ``~/.local/bin``。

    修复 (DEV-0195, 同步异常根因): 后端进程 PATH 常不含 ``~/.local/bin``,
    硬编码 ``"cubox-cli"`` 的 subprocess 直接 FileNotFoundError → 静默返回
    0 条。argv 保持字面量, 改在执行环境上兜底。
    """
    env = os.environ.copy()
    home_local = str(Path.home() / ".local" / "bin")
    if Path(home_local, "cubox-cli").is_file() and home_local not in env.get("PATH", "").split(":"):
        env["PATH"] = f"{home_local}:{env['PATH']}" if env.get("PATH") else home_local
    return env


def _check_cubox_cli() -> bool:
    """Check if cubox-cli is installed (按增强后的 PATH 探测)."""
    return shutil.which("cubox-cli", path=_cubox_env().get("PATH")) is not None


def fetch_cubox_cards(limit: int = 100) -> list[dict]:
    """Fetch cards from cubox-cli.

    Returns list of dicts with keys: title, url, description, tags, create_time
    """
    if not _check_cubox_cli():
        log.warning("cubox-cli not found (增强 PATH 后仍未找到), skipping cubox sync")
        return []

    try:
        result = subprocess.run(
            ["cubox-cli", "card", "list", "-o", "json", "--limit", str(limit)],
            capture_output=True,
            text=True,
            timeout=60,
            env=_cubox_env(),
        )
        if result.returncode != 0:
            log.error(f"cubox-cli failed: {result.stderr}")
            return []
        cards = json.loads(result.stdout)
        if not isinstance(cards, list):
            log.error(
                f"cubox-cli returned non-list JSON: {type(cards).__name__}"
            )
            return []
        log.info(f"cubox-cli returned {len(cards)} cards")
        return cards
    except subprocess.TimeoutExpired:
        log.error("cubox-cli timed out")
        return []
    except json.JSONDecodeError as e:
        log.error(f"cubox-cli JSON parse error: {e}")
        return []
    except Exception as e:
        log.error(f"cubox-cli unexpected error: {e}")
        return []


def _card_to_item(card: dict) -> KnowledgeItem | None:
    """Convert a cubox card to a KnowledgeItem."""
    url = card.get("url", "")
    if not url:
        return None
    item_id = item_id_from_url(url)
    # Prefer article_title (full title) over title (may be truncated).
    title = card.get("article_title") or card.get("title") or "Untitled"
    # Normalize tags: cubox returns list of tag objects or strings.
    raw_tags = card.get("tags", [])
    if isinstance(raw_tags, list):
        tags = [
            t.get("name", "") if isinstance(t, dict) else str(t)
            for t in raw_tags
        ]
        tags = [t for t in tags if t]
    else:
        tags = []
    return KnowledgeItem(
        id=item_id,
        title=title,
        source="cubox",
        source_url=url,
        tags=tags,
        ingested_at=card.get("create_time", now_iso()),
        updated_at=card.get("update_time", now_iso()),
    )


def _write_item_md(item: KnowledgeItem, content: str = "", sources: list[str] | None = None) -> Path:
    """Write a knowledge item to knowledge/items/{id}.md."""
    if sources is None:
        sources = ["cubox"]
    ITEMS_DIR.mkdir(parents=True, exist_ok=True)
    path = ITEMS_DIR / f"{item.id}.md"

    frontmatter = f"""---
id: "{item.id}"
title: "{item.title}"
source: "{item.source}"
source_url: "{item.source_url}"
ingested_at: "{item.ingested_at}"
compiled: false
domain: null
topic: null
type: null
difficulty: null
tags: {json.dumps(item.tags)}
concepts: []
mastery: 0
last_reviewed: null
review_count: 0
related_items: []
sources: {json.dumps(sources)}
---

# {item.title}

{content}
"""
    path.write_text(frontmatter, encoding="utf-8")
    return path


def import_cubox_cards(
    cards: list[dict],
    on_progress=None,
) -> dict:
    """C2 (DEV-0195): 导入 cubox 卡片列表 (单一导入循环, 三条链路共用)。

    数据来源三选一: ①在线同步 (cubox-cli 拉取) ②CLI 导出 JSON 上传 ③本地目录扫描。
    cards 形状 = cubox-cli ``card list -o json`` 输出 (title/article_title/url/
    description/tags/create_time)。

    返回 ``{"new": int, "merged": int, "skipped": int, "total": int}``。
    """
    from backend.repository.knowledge_repo import knowledge_repo
    from backend.services.knowledge_sync import parse_frontmatter

    def _report(current: int, total: int):
        if on_progress:
            on_progress(current, total)

    total_cards = len(cards)
    _report(0, total_cards)
    new_count = 0
    merged_count = 0
    skipped = 0

    for i, card in enumerate(cards):
        item = _card_to_item(card)
        if item is None:
            skipped += 1
            _report(i + 1, total_cards)
            continue

        content = card.get("description", "") or ""
        md_path = ITEMS_DIR / f"{item.id}.md"

        if md_path.exists():
            existing_fm = parse_frontmatter(md_path) or {}
            existing_sources = (
                existing_fm.get("sources", [])
                if isinstance(existing_fm.get("sources"), list)
                else ["cubox"]
            )
            existing_tags = (
                existing_fm.get("tags", [])
                if isinstance(existing_fm.get("tags"), list)
                else []
            )
            merged_sources = list(dict.fromkeys([*existing_sources, "cubox"]))
            merged_tags = list(dict.fromkeys(existing_tags + item.tags))
            _update_md_frontmatter(md_path, merged_sources, merged_tags)
            existing_item = knowledge_repo.get_item(item.id)
            if existing_item:
                existing_item.tags = merged_tags
                existing_item.updated_at = now_iso()
                knowledge_repo.upsert_item(existing_item)
            merged_count += 1
        else:
            if item.source_url:
                similar = find_similar_items(item.source_url)
                if similar:
                    for sid in similar:
                        item.tags.append(f"similar:{sid}")
            _write_item_md(item, content, sources=["cubox"])
            knowledge_repo.upsert_item(item)
            new_count += 1

        _report(i + 1, total_cards)

    log.info(f"cubox cards import: new={new_count}, merged={merged_count}, skipped={skipped}")
    return {
        "new": new_count,
        "merged": merged_count,
        "skipped": skipped,
        "total": new_count + merged_count,
    }


def import_cubox_dir(dir_path: str) -> dict:
    """C2 (DEV-0195): 扫描本地目录中的 cubox CLI 导出 JSON 并导入。

    接受 ``*.json`` 文件, 形状为卡片数组或 ``{"cards": [...]}``;
    其余扩展名忽略。dir_path 必须为绝对路径且为存在的目录 (本地运维导入,
    非出站请求 — 无 SSRF 面; 路径校验防误操作)。
    """
    from pathlib import Path as _P

    p = _P(dir_path).expanduser()
    if not p.is_absolute():
        raise ValueError("path 必须为绝对路径")
    if not p.is_dir():
        raise ValueError(f"目录不存在: {p}")

    files = sorted(p.glob("*.json"))
    all_cards: list[dict] = []
    errors: list[str] = []
    parsed_files = 0
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            errors.append(f"{f.name}: JSON 解析失败 ({e})")
            continue
        if isinstance(data, list):
            all_cards.extend(c for c in data if isinstance(c, dict))
            parsed_files += 1
        elif isinstance(data, dict) and isinstance(data.get("cards"), list):
            all_cards.extend(c for c in data["cards"] if isinstance(c, dict))
            parsed_files += 1
        else:
            errors.append(f"{f.name}: 形状不符 (期望卡片数组或 {{cards: [...]}})")

    result = import_cubox_cards(all_cards)
    return {
        "dir": str(p),
        "files": parsed_files,
        "files_total": len(files),
        "cards": len(all_cards),
        "errors": errors,
        **result,
    }


def sync_cubox_to_knowledge(limit: int = 100) -> int:
    """Sync cubox cards to knowledge/items/*.md.

    Returns number of items written or merged.
    """
    cards = fetch_cubox_cards(limit)
    if not cards:
        return 0
    result = import_cubox_cards(cards)
    return result["total"]


def sync_cubox_with_progress(
    limit: int = 100,
    on_progress=None,
) -> dict:
    """Sync cubox cards with progress callbacks.

    ``on_progress(phase: str, current: int, total: int)`` is called
    at each stage. Returns ``{"new": int, "merged": int, "total": int}``.
    """
    def _report(phase: str, current: int, total: int):
        if on_progress:
            on_progress(phase, current, total)

    _report("fetching", 0, 0)
    cards = fetch_cubox_cards(limit)
    if not cards:
        _report("done", 0, 0)
        return {"new": 0, "merged": 0, "total": 0}

    total_cards = len(cards)
    _report("processing", 0, total_cards)

    def _on_progress(current: int, total: int):
        _report("processing", current, total)

    counts = import_cubox_cards(cards, on_progress=_on_progress)
    new_count = counts["new"]
    merged_count = counts["merged"]

    _report("syncing_db", total_cards, total_cards)
    from backend.services.knowledge_sync import full_sync_concepts_to_db, full_sync_items_to_db
    items_synced = full_sync_items_to_db()
    concepts_synced = full_sync_concepts_to_db()

    _report("done", total_cards, total_cards)
    log.info(
        f"cubox sync with progress: new={new_count}, merged={merged_count}, "
        f"db_items={items_synced}, db_concepts={concepts_synced}"
    )
    return {
        "new": new_count,
        "merged": merged_count,
        "total": new_count + merged_count,
        "items_synced": items_synced,
        "concepts_synced": concepts_synced,
    }


def _update_md_frontmatter(
    path: Path, sources: list[str], tags: list[str]
) -> None:
    """Update sources + tags lines in .md frontmatter, preserving body."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return
    parts = text.split("---", 2)
    if len(parts) < 3:
        return
    frontmatter = parts[1]
    body = parts[2]

    import re

    # Replace or add sources line
    if re.search(r"^sources:", frontmatter, re.MULTILINE):
        frontmatter = re.sub(
            r"^sources:.*$",
            lambda m: f"sources: {json.dumps(sources, ensure_ascii=False)}",
            frontmatter,
            flags=re.MULTILINE,
        )
    else:
        frontmatter = frontmatter.rstrip() + f"\nsources: {json.dumps(sources, ensure_ascii=False)}\n"

    # Replace tags line
    if re.search(r"^tags:", frontmatter, re.MULTILINE):
        frontmatter = re.sub(
            r"^tags:.*$",
            lambda m: f"tags: {json.dumps(tags, ensure_ascii=False)}",
            frontmatter,
            flags=re.MULTILINE,
        )

    path.write_text(f"---{frontmatter}---{body}", encoding="utf-8")
