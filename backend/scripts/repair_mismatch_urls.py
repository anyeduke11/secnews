"""修复 url_check_status='mismatch' 的已入库数据。

逻辑:
1. 拉取所有 url_check_status='mismatch' 的 hotspots
2. 对每个 item 跑 FinalUrlGate 下钻 landing 页 → 真实文章 URL
3. 下钻成功后跑 URLContentGate 验证新 URL 的 <title> 与 item.title 重叠度
4. 验证通过则更新 url + url_check_status='verified' + 追加 flag
5. 下钻失败 / 验证仍 mismatch 则保持原状(查询层已过滤,不会展示)

用法:
    cd /Users/duke/Documents/hotspot
    .venv/bin/python3 backend/scripts/repair_mismatch_urls.py
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from typing import Optional

from backend.config import config as app_config
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.quality.final_url_gate import FinalUrlGate
from backend.quality.url_content_gate import URLContentGate
from backend.repository.db import get_connection


def _row_to_item(row: sqlite3.Row) -> HotspotItem:
    """轻量级反序列化,仅修复脚本使用。"""
    flags_raw = row["quality_flags"]
    flags: list[str] = json.loads(flags_raw) if flags_raw else []
    from datetime import datetime

    ingested_at = None
    raw_ingested = row["ingested_at"] if "ingested_at" in row.keys() else None
    if raw_ingested:
        ingested_at = datetime.fromisoformat(raw_ingested)

    return HotspotItem(
        id=row["id"],
        title=row["title"],
        summary=row["summary"],
        source=row["source"],
        url=row["url"],
        category=Category(row["category"]),
        published_at=datetime.fromisoformat(row["published_at"]),
        score=row["score"],
        fetched_at=datetime.fromisoformat(row["fetched_at"]),
        is_fallback=bool(row["is_fallback"]),
        quality_score=row["quality_score"],
        quality_flags=flags,
        quality_checked_at=None,
        url_check_status=row["url_check_status"],
        ingested_at=ingested_at,
        bid_status=row["bid_status"] if "bid_status" in row.keys() else None,
    )


def _fetch_mismatch_items(conn: sqlite3.Connection) -> list[HotspotItem]:
    rows = conn.execute(
        "SELECT * FROM hotspots WHERE url_check_status = 'mismatch' ORDER BY ingested_at DESC"
    ).fetchall()
    return [_row_to_item(r) for r in rows]


def _update_item(
    conn: sqlite3.Connection,
    item_id: str,
    *,
    url: str,
    url_check_status: str,
    quality_score: int,
    quality_flags: list[str],
) -> None:
    conn.execute(
        "UPDATE hotspots SET url = ?, url_check_status = ?, quality_score = ?, quality_flags = ? WHERE id = ?",
        (
            url,
            url_check_status,
            quality_score,
            json.dumps(quality_flags, ensure_ascii=False),
            item_id,
        ),
    )


async def _repair_item(
    item: HotspotItem, final_gate: FinalUrlGate, content_gate: URLContentGate
) -> tuple[str, Optional[str]]:
    """返回 (新状态, 新URL 或 None)。"""
    original_url = str(item.url)

    # 1. FinalUrlGate 下钻(同步,在 asyncio.to_thread 中跑避免阻塞)
    from backend.quality.base import GateContext

    ctx = GateContext(mode="loose", category_keywords={}, source_reputation={})
    result = await asyncio.to_thread(final_gate.check, item, ctx)

    new_url = str(item.url)
    if result.flags and "url_drilldown_resolved" in result.flags:
        # URL 已被修改
        pass
    elif result.flags and "url_drilldown_no_pattern" in result.flags:
        # 已知域名但无下钻模式,保留原 URL
        return "mismatch", None
    elif not result.passed:
        # 下钻失败
        return "mismatch", None
    else:
        # 已经是最终 URL 或无需下钻
        new_url = original_url

    # 2. URLContentGate 验证新 URL
    content_result = await content_gate.run_async(item)
    if content_result.passed:
        return "verified", new_url
    return "mismatch", None


async def main() -> None:
    conn = get_connection()
    items = _fetch_mismatch_items(conn)
    print(f"发现 {len(items)} 条 url_check_status='mismatch' 数据")

    final_gate = FinalUrlGate(fetch_timeout=5.0)
    content_gate = URLContentGate(timeout=app_config.quality_url_check_timeout)

    fixed = 0
    unchanged = 0
    errors = 0

    for item in items:
        try:
            new_status, new_url = await _repair_item(item, final_gate, content_gate)
            if new_status == "verified" and new_url:
                flags = list(item.quality_flags or [])
                if "url_drilldown_repaired" not in flags:
                    flags.append("url_drilldown_repaired")
                _update_item(
                    conn,
                    item.id,
                    url=new_url,
                    url_check_status="verified",
                    quality_score=item.quality_score,
                    quality_flags=flags,
                )
                fixed += 1
                print(f"[FIXED] {item.id}: {item.title[:40]} -> {new_url[:80]}")
            else:
                unchanged += 1
        except Exception as e:
            errors += 1
            print(f"[ERROR] {item.id}: {e}")

    print(f"\n修复完成: 修复 {fixed} 条, 保持 {unchanged} 条, 错误 {errors} 条")


if __name__ == "__main__":
    asyncio.run(main())
