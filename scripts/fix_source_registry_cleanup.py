"""fix_source_registry_cleanup — 僵尸源与测试残留清理 (采集闭环 T2, 默认 dry-run).

用法::

    .venv/bin/python scripts/fix_source_registry_cleanup.py              # dry-run (默认)
    .venv/bin/python scripts/fix_source_registry_cleanup.py --execute   # 落库

动作 (幂等, 重复执行零变更退出 0):
  1. hotspots 测试残留: DELETE WHERE source IN ('rss', 'test-src')
  2. crawler_sources / custom_sources 同名残留 (若有): DELETE
  3. 僵尸注册行: enabled=0 AND status='unknown' AND last_success_at IS NULL
     (从未 fetch 过的 14 行注册残留) → status='retired' 归档 (不物理删,
     可追溯; enabled 保持 0) + source_alerts(alert_type='source_archived',
     level='P2') 告警, 走 upsert_dedup 防同类重复积累。

DB 访问走 backend.repository 层 (get_connection / SourceAlertRepository)。
核心逻辑抽为可测函数, main 仅薄壳; 测试见
backend/tests/test_fix_source_registry_cleanup.py。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.repository.db import get_connection  # noqa: E402
from backend.repository.source_alert_repo import SourceAlertRepository  # noqa: E402

# 测试残留源标识 (hotspots.source / crawler_sources.id / custom_sources.id)
RESIDUAL_SOURCES: tuple[str, ...] = ("rss", "test-src")

# 僵尸注册行口径: 停用 + 从未进入状态机 (unknown) + 从未成功抓取
ZOMBIE_WHERE = "enabled = 0 AND status = 'unknown' AND last_success_at IS NULL"


def collect_plan(conn) -> dict:
    """只读扫描变更面 (dry-run / execute 共用同一口径)。"""
    marks = ", ".join("?" * len(RESIDUAL_SOURCES))
    residual_hotspots = conn.execute(
        f"SELECT id, source, title FROM hotspots WHERE source IN ({marks})",
        RESIDUAL_SOURCES,
    ).fetchall()
    residual_crawler = conn.execute(
        f"SELECT id, name, status FROM crawler_sources WHERE id IN ({marks})",
        RESIDUAL_SOURCES,
    ).fetchall()
    # custom_sources.id 是自增整数, 同名残留按 name 匹配
    residual_custom = conn.execute(
        f"SELECT id, name FROM custom_sources WHERE name IN ({marks})",
        RESIDUAL_SOURCES,
    ).fetchall()
    zombies = conn.execute(
        f"SELECT id, name, status, enabled FROM crawler_sources WHERE {ZOMBIE_WHERE}"
    ).fetchall()
    return {
        "residual_hotspots": [dict(r) for r in residual_hotspots],
        "residual_crawler": [dict(r) for r in residual_crawler],
        "residual_custom": [dict(r) for r in residual_custom],
        "zombie_sources": [dict(r) for r in zombies],
    }


def apply_plan(conn, plan: dict) -> dict:
    """执行变更 (仅 --execute 调用; 连接为 autocommit, 无需显式 commit)。"""
    marks = ", ".join("?" * len(RESIDUAL_SOURCES))
    cur_hs = conn.execute(
        f"DELETE FROM hotspots WHERE source IN ({marks})", RESIDUAL_SOURCES
    )
    cur_cs = conn.execute(
        f"DELETE FROM crawler_sources WHERE id IN ({marks})", RESIDUAL_SOURCES
    )
    cur_cust = conn.execute(
        f"DELETE FROM custom_sources WHERE name IN ({marks})", RESIDUAL_SOURCES
    )
    zombie_rows = conn.execute(
        f"SELECT id, name FROM crawler_sources WHERE {ZOMBIE_WHERE}"
    ).fetchall()
    cur_z = conn.execute(
        f"UPDATE crawler_sources SET status = 'retired', "
        f"updated_at = datetime('now') WHERE {ZOMBIE_WHERE}"
    )
    alerts = SourceAlertRepository()
    for row in zombie_rows:
        alerts.upsert_dedup({
            "source_id": str(row["id"]),
            "alert_type": "source_archived",
            "level": "P2",
            "message": (
                f"源 {row['name'] or row['id']} 从未抓取成功 (注册残留), "
                f"已归档退役 (retired)"
            ),
            "detail": '{"prev_status": "unknown"}',
        })
    return {
        "hotspots_deleted": cur_hs.rowcount,
        "crawler_sources_deleted": cur_cs.rowcount,
        "custom_sources_deleted": cur_cust.rowcount,
        "zombies_retired": cur_z.rowcount,
        "alerts_written": len(zombie_rows),
    }


def run(conn, *, execute: bool) -> int:
    """扫描 → 报告变更面 → (execute 时) 落库。返回进程退出码。"""
    plan = collect_plan(conn)
    n_hs = len(plan["residual_hotspots"])
    n_cs = len(plan["residual_crawler"])
    n_cust = len(plan["residual_custom"])
    n_z = len(plan["zombie_sources"])

    print(f"[cleanup] hotspots 测试残留 (source IN rss/test-src): {n_hs}")
    for r in plan["residual_hotspots"]:
        print(f"   DELETE hotspots id={r['id']} source={r['source']}")
    print(f"[cleanup] crawler_sources 同名残留: {n_cs}")
    for r in plan["residual_crawler"]:
        print(f"   DELETE crawler_sources id={r['id']} (status={r['status']})")
    print(f"[cleanup] custom_sources 同名残留: {n_cust}")
    for r in plan["residual_custom"]:
        print(f"   DELETE custom_sources id={r['id']}")
    print(f"[cleanup] 僵尸注册行 (unknown+enabled=0+从未成功): {n_z}")
    for r in plan["zombie_sources"]:
        print(f"   RETIRE crawler_sources id={r['id']} ({r['name']}) + source_archived P2")

    total = n_hs + n_cs + n_cust + n_z
    if total == 0:
        print("[cleanup] nothing to do (already clean)")
        return 0
    if not execute:
        print(f"[cleanup] dry-run: {total} 项待处理, 未写入 (加 --execute 落库)")
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
