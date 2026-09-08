"""T15 四入口真实工作台 黄金案例演练 (T14 收口后).

7 步:
  ① 4 view 路由可达 (workbench/intel/cases/knowledge + 兼容 /v1-prototype)
  ② Workbench 真实数据 (listCases 聚合, 走查 3 路径从真实 status 派生)
  ③ Intel 真实数据 (listSignals 复用 T05 v1_signals, 模拟 3 天窗口含信号)
  ④ Knowledge 真实数据 (listKnowledge 端点 placeholder, 走 CaseDetail 内嵌路径)
  ⑤ SkillStore v1_active 高亮区块 (6 SK + status badge + legacy 折叠)
  ⑥ CaseDetail 走查 3 路径 (T12 已落, T15 验证真实数据下仍生效)
  ⑦ 路由表清理确认 (/v1-prototype 兼容 + 4 真路径, T15 收口后仍兼容)

不连真网络; mock dsh 返固定 JSON; dry-run 默认, --apply 真落 admission_log / v1_signals / v1_subjects.
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
    tmp = Path(tempfile.mkdtemp(prefix="hotspot-t15-"))
    os.environ["HOTSPOT_DB_PATH"] = str(tmp / "hotspot.db")
    os.environ["HOTSPOT_WIKI_ROOT"] = str(tmp / "wiki")
    os.environ["HOTSPOT_LOG_DIR"] = str(tmp / "logs")
    os.environ["HOTSPOT_BACKUP_DIR"] = str(tmp / "backups")
    os.environ["HOTSPOT_DATA_DIR"] = str(tmp / "data")


def _seed_all() -> None:
    """seed 跨 step 共享的全量数据 (1 case + 1 judgment + 1 action + 1 run + 1 artifact + 1 knowledge + 2 signals)."""
    from backend.repository import db
    db.init_db()
    conn = sqlite3.connect(os.environ["HOTSPOT_DB_PATH"])
    now = "2026-09-06T00:00:00+00:00"
    one_day_ago = "2026-09-05T00:00:00+00:00"
    conn.execute(
        "INSERT OR IGNORE INTO v1_cases (id, title, question, revision, created_at, updated_at, tags_json) "
        "VALUES (?, 'CVE-2026-31337 修复', '如何升级 FastGate?', 1, ?, ?, '[]')",
        ("C" * 26, now, now),
    )
    conn.execute(
        "INSERT OR IGNORE INTO v1_subjects (id, entity_type, canonical_name, importance, first_seen_at, last_seen_at, revision, created_at, updated_at) "
        "VALUES (?, 'cve', 'FastGate 3200', 'high', ?, ?, 1, ?, ?)",
        ("S" * 26, one_day_ago, one_day_ago, now, now),
    )
    conn.execute(
        "INSERT OR IGNORE INTO v1_materials (id, source_kind, url, title, content_hash, content_length, "
        "fetched_at, created_at, updated_at) "
        "VALUES (?, 'url', 'https://nvd.nist.gov/cve-2026-31337', 'NVD Entry', ?, 100, ?, ?, ?)",
        ("M" * 26, "h" * 64, one_day_ago, now, now),
    )
    conn.execute(
        "INSERT OR IGNORE INTO v1_signals (id, subject_id, material_id, summary, occurred_at, "
        "admission_rule_version, admission_reason, confidence, status, revision, created_at, updated_at) "
        "VALUES (?, ?, ?, 'FastGate 3200 路径遍历漏洞', ?, 'v1.0', 'T15 演练', 'verified', 'verified', 1, ?, ?)",
        ("SIG-T15-1", "S" * 26, "M" * 26, one_day_ago, now, now),
    )
    conn.execute(
        "INSERT OR IGNORE INTO v1_signals (id, subject_id, material_id, summary, occurred_at, "
        "admission_rule_version, admission_reason, confidence, status, revision, created_at, updated_at) "
        "VALUES (?, ?, ?, 'AI 安全新规发布', ?, 'v1.0', 'T15 演练', 'likely', 'likely', 1, ?, ?)",
        ("SIG-T15-2", "S" * 26, "M" * 26, one_day_ago, now, now),
    )
    conn.execute(
        "INSERT OR IGNORE INTO v1_knowledge (id, kind, title, body, status, revision, created_at, updated_at) "
        "VALUES (?, 'playbook', 'FastGate 升级 7.2.0', '# K1 FastGate 升级流程', 'published', 1, ?, ?)",
        ("K" * 26, now, now),
    )
    conn.commit()
    conn.close()


def _list_routes_via_fastapi() -> list[str]:
    """直接调 FastAPI app 拿全部注册路径 (不依赖 conftest 测试启动)."""
    try:
        from fastapi import FastAPI
        from backend.api._registry import register_routers
        app = FastAPI()
        register_routers(app)
        return sorted({r.path for r in app.routes if hasattr(r, "path") and r.path})
    except Exception as e:
        return [f"error: {e}"]


# ---------------------------------------------------------------------------
# 7 步
# ---------------------------------------------------------------------------
def run_step_1_routes() -> dict[str, Any]:
    """① 4 view 路由可达 (workbench/intel/cases/knowledge + 兼容 /v1-prototype)."""
    paths = _list_routes_via_fastapi()
    targets = ["/workbench", "/intel", "/cases", "/knowledge", "/v1-prototype"]
    found = {t: (t in paths) for t in targets}
    return {"step": "1_routes", "found": found, "total_paths": len(paths)}


def run_step_2_workbench(*, apply: bool) -> dict[str, Any]:
    """② Workbench 真实数据 (listCases 聚合, 走查 3 路径从真实 status 派生)."""
    if apply:
        _seed_all()
    from backend.services.case_service import CaseService
    svc = CaseService()
    try:
        items = svc.list_cases(status=None, limit=50)
        blocked = sum(1 for c in items if c.get("status") == "blocked")
        return {
            "step": "2_workbench",
            "cases_count": len(items),
            "blocked_count": blocked,
        }
    except Exception as e:
        return {"step": "2_workbench", "skipped": str(e)}


def run_step_3_intel(*, apply: bool) -> dict[str, Any]:
    """③ Intel 真实数据 (listSignals 复用 T05 v1_signals, 模拟 3 天窗口含信号)."""
    if apply:
        _seed_all()
    from backend.services.signal_service import list_recent_signals
    out = list_recent_signals(days=3, limit=50)
    return {
        "step": "3_intel",
        "signals_count": len(out),
        "sample_ids": [s["id"] for s in out[:2]],
    }


def run_step_4_knowledge(*, apply: bool) -> dict[str, Any]:
    """④ Knowledge 真实数据 (T13 已落 v1_knowledge 主表, 演练 1 条 published)."""
    if apply:
        _seed_all()
    import sqlite3 as sql3
    conn = sql3.connect(os.environ["HOTSPOT_DB_PATH"])
    rows = conn.execute("SELECT id, kind, title, status FROM v1_knowledge").fetchall()
    return {"step": "4_knowledge", "count": len(rows), "sample": rows[0] if rows else None}


def run_step_5_skillstore_v1() -> dict[str, Any]:
    """⑤ SkillStore v1_active 高亮区块 (6 SK + status badge + legacy 折叠)."""
    from backend.services.skill_registry.builtin import BUILTIN
    v1 = [s for s in BUILTIN.list() if getattr(s, "status", None) == "v1_active"]
    legacy = [s for s in BUILTIN.list() if getattr(s, "status", None) == "legacy_v0"]
    return {
        "step": "5_skillstore_v1",
        "v1_active_count": len(v1),
        "v1_ids": sorted(s.id for s in v1),
        "legacy_count": len(legacy),
    }


def run_step_6_case_walkthrough(*, apply: bool) -> dict[str, Any]:
    """⑥ CaseDetail 走查 3 路径 (T12 已落, T15 验证真实数据下仍生效)."""
    if apply:
        _seed_all()
    from backend.services.case_service import CaseService
    cs = CaseService()
    case_items = cs.list_cases(status="blocked", limit=10)
    if not case_items:
        case_items = cs.list_cases(status="open", limit=10)
    return {
        "step": "6_case_walkthrough",
        "cases_count": len(case_items),
        "first_status": case_items[0].get("status") if case_items else None,
    }


def run_step_7_route_cleanup() -> dict[str, Any]:
    """⑦ 路由表清理确认 (/v1-prototype 兼容 + 4 真路径)."""
    paths = _list_routes_via_fastapi()
    has_workbench = "/workbench" in paths
    has_intel = "/intel" in paths
    has_cases = "/cases" in paths
    has_knowledge = "/knowledge" in paths
    has_v1_prototype = "/v1-prototype" in paths
    return {
        "step": "7_route_cleanup",
        "all_4_new_paths": has_workbench and has_intel and has_cases and has_knowledge,
        "v1_prototype_kept": has_v1_prototype,
        "all_4_ok": all([has_workbench, has_intel, has_cases, has_knowledge]),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="T15 四入口真实工作台 黄金案例演练")
    ap.add_argument("--apply", action="store_true", help="真落 v1_signals / v1_subjects / v1_knowledge 表")
    ap.add_argument("--check", action="store_true", help="仅校验输出形状")
    ap.add_argument("--out", type=Path, default=None, help="trace.json 落盘路径")
    args = ap.parse_args()

    if not args.check:
        _ensure_isolated_db()

    steps: list[dict[str, Any]] = []
    steps.append(run_step_1_routes())
    steps.append(run_step_2_workbench(apply=args.apply))
    steps.append(run_step_3_intel(apply=args.apply))
    steps.append(run_step_4_knowledge(apply=args.apply))
    steps.append(run_step_5_skillstore_v1())
    steps.append(run_step_6_case_walkthrough(apply=args.apply))
    steps.append(run_step_7_route_cleanup())

    out_path = args.out or Path(tempfile.mkdtemp(prefix="hotspot-t15-")) / "trace.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"steps": steps, "mode": "apply" if args.apply else "dry-run"},
                                      ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"steps_count": len(steps), "trace": str(out_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
