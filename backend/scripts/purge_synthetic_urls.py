"""Phase 13 — 清理数据库中所有合成 / 真实来源的 fallback 数据 (SPEC §3.3.4)。

执行内容
--------
1. 列出 DB 中 ``is_fallback=1`` 的所有 hotspot,按分类统计
2. 检查每条 item 的 URL 是否命中 §3 硬约束禁止的 pattern
   (example.com / google.com/search / bing.com/search / placeholder.com)
3. 删除命中 pattern 的所有行(连同 favorites 中的关联条目)
4. 输出清理报告(purge_report.json)

使用
----
::

    cd backend
    python scripts/purge_synthetic_urls.py              # 干跑,只输出报告
    python scripts/purge_synthetic_urls.py --apply      # 实际删除
    python scripts/purge_synthetic_urls.py --dry-run    # 等价于不加 --apply

Phase 13 硬约束 (SPEC §3)
--------------------------
资讯 / 标讯卡片上的"原文链接"必须是用户点开就能直接读到该条资讯真实正文的
链接。Phase 12 之前的所有 fallback (example.com / Google 搜索) 都是**禁止**的,
必须清空。

参见
----
* SPEC.md §3 原文链接硬约束
* RCA.md §1 fallback 合成 URL 出现 3 次
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# 禁止的 URL pattern (Phase 13 §3.1.2)
# ---------------------------------------------------------------------------
FORBIDDEN_URL_PATTERNS: list[str] = [
    "example.com",
    "example.org",
    "example.net",
    "placeholder.com",
    "test.com",
    "localhost",
    "google.com/search",
    "bing.com/search",
    "baidu.com/s?",
    "duckduckgo.com/?",
    "yandex.com/search",
]


def is_forbidden_url(url: str) -> str | None:
    """检查 URL 是否命中禁止 pattern。返回命中的 pattern,否则 None。"""
    if not url:
        return None
    lower = url.lower()
    for pat in FORBIDDEN_URL_PATTERNS:
        if pat in lower:
            return pat
    return None


def main() -> int:
    """主入口。"""
    parser = argparse.ArgumentParser(
        description="Phase 13: 清理 DB 中所有合成 / 禁止 pattern URL 的 fallback hotspot"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际执行删除(默认 dry-run)",
    )
    parser.add_argument(
        "--db",
        default="hotspot.db",
        help="DB 文件路径(默认 hotspot.db,相对 backend/ 当前目录)",
    )
    parser.add_argument(
        "--report",
        default="scripts/purge_report.json",
        help="报告输出路径(默认 scripts/purge_report.json)",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"[ERROR] DB file not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # ---- Step 1: 列出所有 is_fallback=1 的 hotspot -----------------
        rows = conn.execute(
            """
            SELECT id, title, url, category, source, fetched_at
            FROM hotspots
            WHERE is_fallback = 1
            ORDER BY category, fetched_at
            """
        ).fetchall()
        all_fallback = [dict(r) for r in rows]
        print(f"[INFO] 找到 is_fallback=1 的 hotspot 共 {len(all_fallback)} 条")

        # ---- Step 2: 检查每条 URL 是否命中禁止 pattern ----------------
        forbidden_matches: list[dict] = []
        for row in all_fallback:
            matched = is_forbidden_url(row["url"])
            if matched:
                row["_matched_pattern"] = matched
                forbidden_matches.append(row)
        print(
            f"[INFO] 命中禁止 URL pattern 的 hotspot: "
            f"{len(forbidden_matches)} / {len(all_fallback)}"
        )

        # ---- Step 2.5: Phase 13 严格模式 - 删所有 is_fallback=True ------
        # SPEC §3.1.2 / §3.6 严格规定: fallback 数据本身就是禁止的。
        # 即使 URL 不命中禁止 pattern (e.g. github _extract_repo_url 提取的
        # owner/repo URL),只要 is_fallback=True 就必须清理 — 因为 fallback
        # 数据是历史 Phase 9 的硬编码合成产物,违反"原文链接必须真实"约束。
        rows_to_delete = list(all_fallback)
        print(
            f"[INFO] Phase 13 严格模式: 将删除所有 is_fallback=1 的 hotspot: "
            f"{len(rows_to_delete)} 条 (含禁止 URL {len(forbidden_matches)} 条 "
            f"+ 其他残留 {len(all_fallback) - len(forbidden_matches)} 条)"
        )

        # ---- Step 3: 按 category 统计 -------------------------------
        by_category: dict[str, int] = {}
        for row in rows_to_delete:
            cat = row.get("category", "unknown")
            by_category[cat] = by_category.get(cat, 0) + 1

        # ---- Step 4: 实际删除(如果 --apply) -------------------------
        deleted_ids: list[str] = []
        deleted_favorite_rows = 0
        if args.apply and rows_to_delete:
            print(f"[INFO] --apply 模式: 即将删除 {len(rows_to_delete)} 条 hotspot")
            ids_to_delete = [r["id"] for r in rows_to_delete]
            for hid in ids_to_delete:
                # 先清 favorites(防 FK 失败)
                fav_rows = conn.execute(
                    "DELETE FROM favorites WHERE hotspot_id = ?", (hid,)
                ).rowcount
                deleted_favorite_rows += fav_rows
                # 删主表
                main_rows = conn.execute(
                    "DELETE FROM hotspots WHERE id = ?", (hid,)
                ).rowcount
                if main_rows > 0:
                    deleted_ids.append(hid)
            conn.commit()
            print(
                f"[INFO] 已删除 hotspot {len(deleted_ids)} 条, "
                f"关联 favorites {deleted_favorite_rows} 条"
            )
        elif not args.apply:
            print(
                f"[DRY-RUN] 未应用任何变更。加上 --apply 参数实际执行删除。\n"
                f"  删除 hotspot: {len(rows_to_delete)} 条\n"
                f"  按分类: {by_category}"
            )

        # ---- Step 6: 写报告 ----------------------------------------
        report = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "db_path": str(db_path),
            "applied": args.apply,
            "fallback_total": len(all_fallback),
            "forbidden_url_matches": len(forbidden_matches),
            "by_category": by_category,
            "deleted_hotspot_count": len(deleted_ids),
            "deleted_favorite_count": deleted_favorite_rows,
            "phase13_strict_mode": True,
            "forbidden_patterns": FORBIDDEN_URL_PATTERNS,
            "note": "Phase 13 严格模式: 删除所有 is_fallback=1 的 hotspot,不仅是命中禁止 pattern 的"
        }
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[INFO] 报告已写入: {report_path}")

        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
