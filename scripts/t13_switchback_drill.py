#!/usr/bin/env python3
"""C13 切换回退演练 (基于 t02 backup_drill 模式).

演练步骤 (模拟生产 v1.0 上线后回退到 v0.x):
  1) 备份 manifest (C01 备份链) — 检查 manifest 完整
  2) v1 新增 1 case (走 v1_cases) — 模拟生产增量
  3) 切回 v0.x (走 C01 备份恢复) — dry-run 模拟
  4) v1 新增 case 仍可读 — 验证 v1 数据保真

用法:
  python scripts/t13_switchback_drill.py --execute  # 真跑 (写 log)
  python scripts/t13_switchback_drill.py --dry-run  # 默认, 仅打印步骤

C13 plan §4.1: 切回演练脚本 (基于 backup-drill.md 模板).
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.config import config
from backend.logging_config import logger
from backend.repository.db import get_connection

DRILL_STEPS = [
    "1) 备份 manifest (C01 备份链) — 检查 manifest 完整",
    "2) v1 新增 1 case (走 v1_cases) — 模拟生产增量",
    "3) 切回 v0.x (走 C01 备份恢复) — dry-run 模拟",
    "4) v1 新增 case 仍可读 — 验证 v1 数据保真",
]


def _check_backup_manifest() -> dict:
    """检查 C01 备份 manifest 是否存在 (生产路径 /path/to/hotspot/data/backup)."""
    backup_dir = Path(getattr(config, "backup_dir", REPO_ROOT / "data" / "backup"))
    if not backup_dir.exists():
        return {"step": 1, "ok": False, "error": f"backup dir not found: {backup_dir}"}
    manifests = list(backup_dir.glob("*.manifest.json"))
    if not manifests:
        return {"step": 1, "ok": False, "error": "no .manifest.json in backup dir"}
    return {"step": 1, "ok": True, "manifests": [m.name for m in manifests[:3]]}


def _add_v1_case() -> dict:
    """v1 新增 1 case (走 v1_cases), 模拟生产 v1 增量."""
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    case_id = f"C13DRILL{datetime.now(timezone.utc).strftime('%H%M%S')}"
    try:
        conn.execute(
            "INSERT INTO v1_cases (id, title, status, owner, severity, created_at, updated_at) "
            "VALUES (?, ?, 'open', 'c13-drill', 'info', ?, ?)",
            (case_id, "C13 switchback drill case", now, now),
        )
        conn.commit()
        return {"step": 2, "ok": True, "case_id": case_id}
    except Exception as e:
        return {"step": 2, "ok": False, "error": str(e)}


def _simulate_v0_restore() -> dict:
    """切回 v0.x dry-run 模拟 (不动真实数据, 仅打印步骤)."""
    return {
        "step": 3, "ok": True,
        "note": "dry-run 模拟: 真实切换需停 v1 → restore C01 备份 → 检查 v1 增量",
        "actions": [
            "stop v1 backend (kill :8000)",
            "restore hot.db from backup_manifest latest",
            "verify v0.x schema 仍在 (3780 行 warm.knowledge_items)",
        ],
    }


def _verify_v1_case(case_id: str) -> dict:
    """v1 新增 case 仍可读 (走 v1_cases SELECT)."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id, title, status, owner FROM v1_cases WHERE id = ?", (case_id,),
    ).fetchone()
    if not row:
        return {"step": 4, "ok": False, "error": f"case {case_id} not found after switchback"}
    return {"step": 4, "ok": True, "case": {"id": row[0], "title": row[1], "status": row[2], "owner": row[3]}}


def main() -> int:
    p = argparse.ArgumentParser(description="C13 切换回退演练")
    p.add_argument("--execute", action="store_true", help="真跑 (会写 v1_cases 增量 + audit_log)")
    p.add_argument("--dry-run", action="store_true", help="默认, 仅打印 4 步")
    args = p.parse_args()

    if args.dry_run or not args.execute:
        print("=== C13 切换回退演练 (DRY-RUN) ===")
        for s in DRILL_STEPS:
            print(s)
        return 0

    print("=== C13 切换回退演练 (EXECUTE) ===")
    results: list[dict] = []
    # step 1
    r1 = _check_backup_manifest()
    print(f"[step 1] {'OK' if r1['ok'] else 'FAIL'}: {r1}")
    results.append(r1)
    if not r1["ok"]:
        return 1
    # step 2
    r2 = _add_v1_case()
    print(f"[step 2] {'OK' if r2['ok'] else 'FAIL'}: {r2}")
    results.append(r2)
    if not r2["ok"]:
        return 2
    # step 3
    r3 = _simulate_v0_restore()
    print(f"[step 3] {'OK' if r3['ok'] else 'FAIL'}: {r3}")
    results.append(r3)
    # step 4
    r4 = _verify_v1_case(r2["case_id"])
    print(f"[step 4] {'OK' if r4['ok'] else 'FAIL'}: {r4}")
    results.append(r4)

    # audit_log 记录演练结果
    try:
        from backend.observability_records import record_audit
        record_audit(
            actor="c13_switchback_drill",
            action="drill.complete",
            target="v1.0-switchback",
            detail={"results": results, "executed_at": datetime.now(timezone.utc).isoformat()},
        )
    except Exception as e:
        logger.warning(f"audit_log write failed: {e}")

    ok = all(r.get("ok") for r in results)
    print(f"\n=== {'PASS' if ok else 'FAIL'} ===")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
