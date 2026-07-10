"""Phase 47: 清理 DB 中历史资讯 (published_at 早于本周一 00:00 Shanghai)。

目的
----
用户 2026-07-10 反馈: 嘶吼等源抓取把历史资讯混入首页。Phase 47 修复后,
新增抓取会被 RecencyGate 拦截, 但已入库的历史资讯仍需清理。

策略
----
1. ``published_at < 本周一 00:00:00 Asia/Shanghai`` 的记录 → 标 flag
   ``historical_published`` + quality_score=0, 列表 query 会自动过滤。
   范围: 150 条 (跨 7 个 source)。

2. 嘶吼 40 条**flag** (``--flag-sihou``) — 嘶吼无 RSS, 旧数据
   ``published_at = fetch time fallback``, 但内容含大量历史资讯
   (如 "2025年勒索软件" / "COVID-19 越南 APT32" / "2024 京ICP")。
   flag 标 ``historical_published`` + score=0, 列表 query 自动过滤。
   (不直接 DELETE, 留作 Phase 47 新抓取行为后的对照。)

用法
----
    # Dry-run (默认, 打印影响)
    python scripts/cleanup_historical_published.py

    # 实际 flag 150 条历史资讯
    python scripts/cleanup_historical_published.py --apply

    # 额外 flag 嘶吼 40 条 fetch-time-fallback 旧数据
    python scripts/cleanup_historical_published.py --apply --flag-sihou

安全
----
- 默认 dry-run, ``--apply`` 才写库
- 写在单事务内, 失败回滚
- 不可逆 (UPDATE 不易撤销, DELETE 完全不可逆)
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DB_PATH = Path(__file__).resolve().parent.parent / "backend" / "hotspot.db"
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _current_week_start_utc() -> str:
    """返回「本周一 00:00 Asia/Shanghai」对应 UTC ISO 字符串 (用于 SQLite 字典序比较)."""
    now_sh = datetime.now(SHANGHAI_TZ)
    monday_sh = now_sh.replace(
        hour=0, minute=0, second=0, microsecond=0
    ) - timedelta(days=now_sh.weekday())
    monday_utc = monday_sh.astimezone(timezone.utc)
    return monday_utc.isoformat()


def _add_flag(quality_flags_json: str | None, new_flag: str) -> str:
    """在 JSON 数组 (SQLite TEXT 形式) 中追加 flag."""
    if not quality_flags_json or quality_flags_json in ("null", "[]"):
        return json.dumps([new_flag], ensure_ascii=False)
    try:
        arr = json.loads(quality_flags_json)
    except (json.JSONDecodeError, TypeError):
        return json.dumps([new_flag], ensure_ascii=False)
    if not isinstance(arr, list):
        return json.dumps([new_flag], ensure_ascii=False)
    if new_flag in arr:
        return quality_flags_json
    arr.append(new_flag)
    return json.dumps(arr, ensure_ascii=False)


def main() -> int:
    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}")
        return 1

    threshold_utc = _current_week_start_utc()
    flag_sihou = "--flag-sihou" in sys.argv
    apply = "--apply" in sys.argv

    print(f"Phase 47 cleanup")
    print(f"  week_start_utc: {threshold_utc}")
    print(f"  mode: {'APPLY' if apply else 'DRY-RUN'}")
    print(f"  flag_sihou: {flag_sihou}")
    print()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # ---- Stage 1: published_at 早于本周一 (DB 中存的是 UTC 字符串, 字典序比较) ----
    old_rows = conn.execute(
        """
        SELECT id, source, category, title, published_at, quality_flags
        FROM hotspots
        WHERE published_at < ?
          AND (quality_flags IS NULL
               OR quality_flags NOT LIKE '%historical_published%')
        ORDER BY source, published_at
        """,
        (threshold_utc,),
    ).fetchall()

    by_source: dict[str, int] = {}
    for r in old_rows:
        by_source[r["source"]] = by_source.get(r["source"], 0) + 1

    print(f"【1】published_at < 本周一 00:00 UTC 记录: {len(old_rows)} 条")
    for src, n in sorted(by_source.items(), key=lambda x: -x[1]):
        print(f"    {src:<20} | {n} 条")

    target_ids: set[str] = {r["id"] for r in old_rows}

    # ---- Stage 2 (可选): 嘶吼 fetch-time-fallback 旧数据 flag ----
    sihou_count = 0
    if flag_sihou:
        sihou_rows = conn.execute(
            """
            SELECT id, title FROM hotspots
            WHERE source = '嘶吼'
              AND (quality_flags IS NULL
                   OR quality_flags NOT LIKE '%historical_published%')
            ORDER BY id
            """,
        ).fetchall()
        sihou_count = len(sihou_rows)
        print()
        print(f"【2】嘶吼 source 记录待 flag: {sihou_count} 条")
        if sihou_count and sihou_count <= 50:
            for r in sihou_rows:
                print(f"    {r['id']:<35} | {r['title'][:50]}")
        elif sihou_count:
            for r in sihou_rows[:5]:
                print(f"    {r['id']:<35} | {r['title'][:50]}")
            print(f"    ... ({sihou_count - 5} more)")

    # ---- 总结 ----
    print()
    if not apply:
        print(f"【合】flag 目标: {len(target_ids)} 条")
        if flag_sihou:
            print(f"【合】额外 flag 目标: {sihou_count} 条 (嘶吼)")
        print()
        print("Dry-run mode. Re-run with --apply to execute.")
        if flag_sihou:
            print("  python scripts/cleanup_historical_published.py --apply --flag-sihou")
        else:
            print("  python scripts/cleanup_historical_published.py --apply")
        conn.close()
        return 0

    # ---- Apply: 单事务 ----
    print()
    print("Applying cleanup (single transaction)...")

    try:
        conn.execute("BEGIN")

        # Stage 1: UPDATE flag + score=0
        for tid in target_ids:
            cur = conn.execute(
                "SELECT quality_flags FROM hotspots WHERE id = ?", (tid,)
            ).fetchone()
            new_flags = _add_flag(cur["quality_flags"] if cur else None, "historical_published")
            conn.execute(
                "UPDATE hotspots SET quality_flags = ?, quality_score = 0 WHERE id = ?",
                (new_flags, tid),
            )
        print(f"  Stage 1 done: flagged {len(target_ids)} historical records")

        # Stage 2 (optional): flag 嘶吼
        if flag_sihou:
            sihou_flagged = 0
            for r in sihou_rows:
                cur = conn.execute(
                    "SELECT quality_flags FROM hotspots WHERE id = ?", (r["id"],)
                ).fetchone()
                new_flags = _add_flag(cur["quality_flags"] if cur else None, "historical_published")
                conn.execute(
                    "UPDATE hotspots SET quality_flags = ?, quality_score = 0 WHERE id = ?",
                    (new_flags, r["id"]),
                )
                sihou_flagged += 1
            print(f"  Stage 2 done: flagged {sihou_flagged} 嘶吼 records")

        conn.execute("COMMIT")
        print("Committed.")
    except Exception as e:
        conn.execute("ROLLBACK")
        print(f"FAILED: {e}; rolled back.")
        conn.close()
        return 1

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
