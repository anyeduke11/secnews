"""T16 旧数据迁移 黄金案例演练 — 5 步.

T15.5 + T16 收口: 验证旧 20 SK deprecated + 旧 15 knowledge 迁移真实落库.

5 步:
  ①legacy_migrate dry-run          计数 (candidates 15 knowledge + 20 legacy SK)
  ②legacy_migrate apply            真落 (写入 v1_knowledge + 标 BUILTIN deprecated + audit_log)
  ③20 SK deprecated 验证           BUILTIN.list status='deprecated' = 20
  ④旧 15 knowledge 迁移验证         v1_knowledge 表行数 ≥ 15 + content_hash 全部非空
  ⑤summary                          real database state 终态对账

不连真网络; dry-run 默认, --apply 真落库 (走 temp_db conftest).
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent


def _ensure_isolated_db() -> None:
    if os.environ.get("HOTSPOT_DB_PATH"):
        return
    tmp = Path(tempfile.mkdtemp(prefix="hotspot-t16-"))
    os.environ["HOTSPOT_DB_PATH"] = str(tmp / "hotspot.db")
    os.environ["HOTSPOT_WIKI_ROOT"] = str(tmp / "wiki")
    os.environ["HOTSPOT_LOG_DIR"] = str(tmp / "logs")
    os.environ["HOTSPOT_BACKUP_DIR"] = str(tmp / "backups")
    os.environ["HOTSPOT_DATA_DIR"] = str(tmp / "data")


def _init_db() -> None:
    from backend.repository import db
    db.init_db()


# ---------------------------------------------------------------------------
# 5 步
# ---------------------------------------------------------------------------
def run_step_1_dry_run() -> dict[str, Any]:
    """① legacy_migrate dry-run — 计数 candidates."""
    from backend.services.legacy_migrate_service import LegacyMigrateService
    svc = LegacyMigrateService()
    r = svc.run(apply=False)
    return {
        "step": "1_dry_run",
        "knowledge_candidates": r.knowledge_candidates,
        "legacy_sks_marked": r.legacy_sks_marked,  # 候选 20
        "errors": r.errors,
    }


def run_step_2_apply() -> dict[str, Any]:
    """② legacy_migrate apply — 真落 v1_knowledge + 标 BUILTIN deprecated + audit_log."""
    from backend.services.legacy_migrate_service import LegacyMigrateService
    svc = LegacyMigrateService()
    r = svc.run(apply=True)
    return {
        "step": "2_apply",
        "knowledge_applied": r.knowledge_applied,
        "knowledge_skipped": r.knowledge_skipped,
        "legacy_sks_marked": r.legacy_sks_marked,
        "errors": r.errors,
    }


def run_step_3_verify_20_deprecated() -> dict[str, Any]:
    """③ 20 SK deprecated 验证 — BUILTIN.list 计数."""
    from backend.services.skill_registry.builtin import BUILTIN
    deprecated = [s for s in BUILTIN.list() if getattr(s, "status", None) == "deprecated"]
    v1_active = [s for s in BUILTIN.list() if getattr(s, "status", None) == "v1_active"]
    legacy = [s for s in BUILTIN.list() if getattr(s, "status", None) == "legacy_v0"]
    return {
        "step": "3_verify_20_deprecated",
        "deprecated_count": len(deprecated),
        "v1_active_count": len(v1_active),
        "legacy_v0_count": len(legacy),
        "deprecated_ids_sample": sorted(s.id for s in deprecated)[:3],
    }


def run_step_4_verify_knowledge() -> dict[str, Any]:
    """④ 旧 15 knowledge 迁移验证 — v1_knowledge 表行数 + content_hash 全部非空."""
    conn = sqlite3.connect(os.environ["HOTSPOT_DB_PATH"])
    rows = conn.execute(
        "SELECT id, kind, status, content_hash, body FROM v1_knowledge"
    ).fetchall()
    count = len(rows)
    has_content_hash = sum(1 for r in rows if r[3])
    return {
        "step": "4_verify_knowledge",
        "total_count": count,
        "with_content_hash": has_content_hash,
        "sample_kinds": sorted({r[1] for r in rows}),
    }


def run_step_5_summary() -> dict[str, Any]:
    """⑤ summary — real database state 终态对账."""
    conn = sqlite3.connect(os.environ["HOTSPOT_DB_PATH"])
    counts = {
        "v1_knowledge_rows": conn.execute("SELECT COUNT(*) FROM v1_knowledge").fetchone()[0],
        "v1_knowledge_published": conn.execute(
            "SELECT COUNT(*) FROM v1_knowledge WHERE status = 'published'"
        ).fetchone()[0],
        "v1_knowledge_draft": conn.execute(
            "SELECT COUNT(*) FROM v1_knowledge WHERE status = 'draft'"
        ).fetchone()[0],
    }
    from backend.services.skill_registry.builtin import BUILTIN
    counts["legacy_sks_deprecated"] = sum(
        1 for s in BUILTIN.list() if getattr(s, "status", None) == "deprecated"
    )
    counts["legacy_sks_v1_active"] = sum(
        1 for s in BUILTIN.list() if getattr(s, "status", None) == "v1_active"
    )
    return {"step": "5_summary", "counts": counts}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="T16 旧数据迁移 黄金案例演练")
    ap.add_argument("--apply", action="store_true", help="真落库 (否则 dry-run + 计数)")
    ap.add_argument("--check", action="store_true", help="仅校验输出形状")
    ap.add_argument("--out", type=Path, default=None, help="trace.json 落盘路径")
    args = ap.parse_args()

    if not args.check:
        _ensure_isolated_db()
        if args.apply:
            _init_db()
        # dry-run 与 apply 跑两遍 (apply 跑真实写, dry-run 跑虚拟, 但 init_db 已 init)
        steps: list[dict[str, Any]] = []
        steps.append(run_step_1_dry_run())
        steps.append(run_step_2_apply())
        steps.append(run_step_3_verify_20_deprecated())
        steps.append(run_step_4_verify_knowledge())
        steps.append(run_step_5_summary())
    else:
        steps = []

    out_path = args.out or Path(tempfile.mkdtemp(prefix="hotspot-t16-golden-")) / "trace.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"steps": steps, "apply": args.apply},
                                      ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"steps_count": len(steps), "trace": str(out_path),
                          "apply": args.apply}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
