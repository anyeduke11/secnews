"""fix_source_stats_cleanup — 统计层死源空壳清理 (数据源治理 T2, 默认 dry-run).

用法::

    .venv/bin/python3 scripts/fix_source_stats_cleanup.py              # dry-run (默认)
    .venv/bin/python3 scripts/fix_source_stats_cleanup.py --execute   # 落库

动作 (幂等, 重复执行零变更退出 0):
  source_stats 中 status='dead' AND total_items=0 的行 (从未产出 = 与供给
  目标无实质关联的空壳注册, 实测 2026-09-26 为 56 行) → 逐行先写
  source_cleanup_log(source_layer='source_stats',
  source_ident=source_name 或 source_url, reason='never_yielded_dead_cleanup',
  executed_by='fix_source_stats_cleanup') 再 DELETE。

不清理 (设计稿 §3.2 裁决):
  - 12 个有产出的 dead (total_items > 0, 复活探测覆盖)
  - stale / active 行与 crawler_sources 注册层 (retired 15 行是健康机资产)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.repository.db import get_connection  # noqa: E402
from backend.repository.source_cleanup_log_repo import SourceCleanupLogRepository  # noqa: E402

# 清理口径: 判死 且 从未产出 (空壳注册)
DEAD_EMPTY_WHERE = "status = 'dead' AND total_items = 0"


def collect_plan(conn) -> list[dict]:
    """只读扫描变更面 (dry-run / execute 共用同一口径)。"""
    rows = conn.execute(
        f"SELECT id, category, source_name, source_url FROM source_stats "
        f"WHERE {DEAD_EMPTY_WHERE} ORDER BY category, source_name"
    ).fetchall()
    return [dict(r) for r in rows]


def _ident(row: dict) -> str:
    """行标识: 优先 source_name, 缺失回落 source_url, 再回落主键。"""
    return str(row.get("source_name") or row.get("source_url") or f"row:{row['id']}")


def apply_plan(conn, plan: list[dict]) -> dict:
    """执行变更 (仅 --execute 调用; 连接为 autocommit, 无需显式 commit)。"""
    audit = SourceCleanupLogRepository()
    for row in plan:
        # 审计强制: 先写 log 再删
        audit.add(
            source_layer="source_stats",
            source_ident=_ident(row),
            reason="never_yielded_dead_cleanup",
            executed_by="fix_source_stats_cleanup",
        )
        conn.execute("DELETE FROM source_stats WHERE id = ?", (row["id"],))
    return {"audited_and_deleted": len(plan)}


def run(conn, *, execute: bool) -> int:
    """扫描 → 报告变更面 → (execute 时) 落库。返回进程退出码。"""
    plan = collect_plan(conn)
    print(f"[cleanup] source_stats 空壳死源 (dead AND total_items=0): {len(plan)}")
    for r in plan:
        print(f"   DELETE source_stats id={r['id']} [{r['category']}] {_ident(r)}")
    if not plan:
        print("[cleanup] nothing to do (already clean)")
        return 0
    if not execute:
        print(f"[cleanup] dry-run: {len(plan)} 行待清理, 未写入 (加 --execute 落库)")
        return 0
    result = apply_plan(conn, plan)
    print(f"[cleanup] applied: {result}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--execute",
        action="store_true",
        help="真实写入 (默认 dry-run, 只报告变更面不落库)",
    )
    args = ap.parse_args(argv)
    return run(get_connection(), execute=args.execute)


if __name__ == "__main__":
    raise SystemExit(main())
