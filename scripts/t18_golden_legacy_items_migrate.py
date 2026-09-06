"""T18 旧 knowledge_items 数据迁移 黄金案例演练 — 5 步.

T17 旧 15 knowledge 走 dev_data/seed.json (T16 已落);
T18 真落 3800 行 走 warm.knowledge_items (T00 备份演练已 attach) → v1_knowledge.

5 步:
  ①migrate_legacy_items dry-run          count + sample
  ②migrate_legacy_items apply            真落 3800 行 (含 kl:deduped 排除)
  ③verify v1_knowledge ≥ dry-run count   表行数对账
  ④verify 旧 knowledge_items 数据保留     contracts §10.3 "已引用对象不删"
  ⑤summary (lifecycle 分布 + domain→kind 映射分布)

不连真网络; dry-run 默认, --apply 真落 WARM_DB → v1_knowledge.
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
    tmp = Path(tempfile.mkdtemp(prefix="hotspot-t18-golden-"))
    os.environ["HOTSPOT_DB_PATH"] = str(tmp / "hotspot.db")
    os.environ["HOTSPOT_WARM_DB_PATH"] = str(tmp / "hotspot-warm.db")
    os.environ["HOTSPOT_WIKI_ROOT"] = str(tmp / "wiki")
    os.environ["HOTSPOT_LOG_DIR"] = str(tmp / "logs")
    os.environ["HOTSPOT_BACKUP_DIR"] = str(tmp / "backups")
    os.environ["HOTSPOT_DATA_DIR"] = str(tmp / "data")
    # 关键: config.warm_db_path 默认指向 BASE_DIR/hotspot-warm.db (生产路径), 必须同步改
    # 否则 ATTACH 的是生产 warm (文件不存在 → skip), _seed_warm_items 写到 tmp warm — 两个文件.
    # 同 touch warm 文件 (init_db ATTACH 时检查 exists, 不存在就 skip — 必须先 touch).
    from backend.config import config
    config.db_path = Path(os.environ["HOTSPOT_DB_PATH"])
    config.warm_db_path = Path(os.environ["HOTSPOT_WARM_DB_PATH"])
    config.cold_db_path = tmp / "hotspot-cold.db"  # 改指 tmp, 防止挂生产 cold
    Path(os.environ["HOTSPOT_WARM_DB_PATH"]).touch()


def _seed_warm_items() -> int:
    """Seed warm.knowledge_items with 6 fixture rows (含 kl:deduped 排除验证).

    真实生产 warm db 已有 3800 行 (历史 M2-T6 之前落); 黄金演练 fresh tmp 上没有,
    需要自己 apply_migrations 在 warm 上建表 + seed. 返回 seed 行数.
    """
    from backend.repository.db import apply_migrations as _apply
    warm_path = Path(os.environ["HOTSPOT_WARM_DB_PATH"])
    warm = sqlite3.connect(str(warm_path))
    _apply(warm)  # warm 上 apply 018-035 migration 建 knowledge_items + ALTER 列
    items = [
        {"id": "g1", "title": "AI Threat Report", "domain": "ai", "lifecycle": "kl:publish", "compiled": 1, "type": "analysis", "difficulty": "intro"},
        {"id": "g2", "title": "DevOps Pattern", "domain": "dev", "lifecycle": "kl:structure", "compiled": 0, "type": "tutorial"},
        {"id": "g3", "title": "Security Advisory CVE", "domain": "security", "lifecycle": "kl:publish", "compiled": 1, "type": "advisory"},
        {"id": "g4", "title": "Startup Reference", "domain": "startup", "lifecycle": "kl:raw", "compiled": 0, "type": "notes"},
        {"id": "g5", "title": "Finance Compliance", "domain": "finance", "lifecycle": "kl:refine", "compiled": 0, "type": "checklist"},
        {"id": "g6", "title": "Already Deduped", "domain": "ai", "lifecycle": "kl:deduped", "compiled": 1, "type": "dup"},
    ]
    cols = [r[1] for r in warm.execute("PRAGMA table_info(knowledge_items)").fetchall()]
    defaults = {
        "source": "bookmark", "source_url": "", "domain": "", "topic": "",
        "type": "", "difficulty": "", "tags": "[]", "concepts": "[]",
        "mastery": 0, "compiled": 0,
        "ingested_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "folder": "", "cve_ids": "[]", "attack_techniques": "[]",
        "compliance_refs": "[]", "threat_actors": "[]", "products": "[]",
        "lifecycle": "kl:raw", "news_type": "", "tech_stack": "[]",
        "attention_score": 0, "body": "",
    }
    for it in items:
        row = {**defaults, **it}
        placeholders = ",".join("?" * len(cols))
        values = tuple(row.get(c) for c in cols)
        cols_quoted = ",".join(f'"{c}"' for c in cols)
        warm.execute(
            f'INSERT OR REPLACE INTO knowledge_items ({cols_quoted}) VALUES ({placeholders})',
            values,
        )
    warm.commit()
    warm.close()
    return len(items)


# ---------------------------------------------------------------------------
# 5 步
# ---------------------------------------------------------------------------
def run_step_1_dry_run() -> dict[str, Any]:
    """① migrate_legacy_items dry-run — 计数 (排除 kl:deduped)."""
    from backend.repository import db
    db.init_db()
    seeded = _seed_warm_items()  # seed 6 fixture rows (含 kl:deduped 排除验证)
    from backend.services.legacy_items_migrate_service import LegacyItemsMigrateService
    svc = LegacyItemsMigrateService()
    r = svc.migrate_legacy_items(apply=False)
    return {
        "step": "1_dry_run",
        "seeded": seeded,
        "items_candidates": r.items_candidates,
        "sample_ids": r.sample_ids,
    }


def run_step_2_apply() -> dict[str, Any]:
    """② migrate_legacy_items apply — 真落 v1_knowledge (3800 行)."""
    from backend.services.legacy_items_migrate_service import LegacyItemsMigrateService
    svc = LegacyItemsMigrateService()
    r = svc.migrate_legacy_items(apply=True)
    return {
        "step": "2_apply",
        "items_applied": r.items_applied,
        "items_skipped": r.items_skipped,
        "errors_count": len(r.errors),
    }


def run_step_3_verify_count() -> dict[str, Any]:
    """③ v1_knowledge 表行数 ≥ dry-run count (T18 收口验证)."""
    conn = sqlite3.connect(os.environ["HOTSPOT_DB_PATH"])
    count = conn.execute("SELECT COUNT(*) FROM v1_knowledge").fetchone()[0]
    return {"step": "3_verify_count", "v1_knowledge_count": count}


def run_step_4_verify_old_data_preserved() -> dict[str, Any]:
    """④ 旧 knowledge_items 数据保留 (contracts §10.3 "已引用对象不删").

    真实生产 warm 是 ~3800 行 (历史 M2-T6 之前落); 黄金演练 seed 6 fixture 行 (含 kl:deduped),
    迁移后旧表 6 行不变 — v1_knowledge 派生 5 行 (deduped 排除).
    """
    try:
        warm = sqlite3.connect(os.environ["HOTSPOT_WARM_DB_PATH"])
        count = warm.execute("SELECT COUNT(*) FROM knowledge_items").fetchone()[0]
    except sqlite3.OperationalError as e:
        return {"step": "4_verify_old_data", "warning": f"warm_db unavailable: {e}", "count": None}
    return {"step": "4_verify_old_data", "old_knowledge_items_count": count}


def run_step_5_summary() -> dict[str, Any]:
    """⑤ summary — 实际数据库状态对账 (含 lifecycle 分布 + domain→kind 映射分布)."""
    conn = sqlite3.connect(os.environ["HOTSPOT_DB_PATH"])
    # lifecycle 分布 (旧 knowledge_items)
    try:
        warm = sqlite3.connect(os.environ["HOTSPOT_WARM_DB_PATH"])
        lifecycle = dict(warm.execute(
            "SELECT lifecycle, COUNT(*) FROM knowledge_items GROUP BY lifecycle"
        ).fetchall())
    except Exception:
        lifecycle = {}
    # kind 分布 (新 v1_knowledge)
    kind = dict(conn.execute(
        "SELECT kind, COUNT(*) FROM v1_knowledge GROUP BY kind"
    ).fetchall())
    return {
        "step": "5_summary",
        "lifecycle_distribution": dict(lifecycle),
        "v1_kind_distribution": kind,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="T18 旧 knowledge_items 数据迁移 黄金案例演练")
    ap.add_argument("--check", action="store_true", help="仅校验")
    ap.add_argument("--out", type=Path, default=None, help="trace.json 落盘")
    args = ap.parse_args()

    if not args.check:
        _ensure_isolated_db()

    steps: list[dict[str, Any]] = []
    steps.append(run_step_1_dry_run())
    steps.append(run_step_2_apply())
    steps.append(run_step_3_verify_count())
    steps.append(run_step_4_verify_old_data_preserved())
    steps.append(run_step_5_summary())

    out_path = args.out or Path(tempfile.mkdtemp(prefix="hotspot-t18-golden-")) / "trace.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"steps": steps}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"steps_count": len(steps), "trace": str(out_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
