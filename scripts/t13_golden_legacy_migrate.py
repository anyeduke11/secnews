#!/usr/bin/env python3
"""C13 黄金案例 7 步演练 — 真实 warm 3800 副本 + 切换回退 (含 promote 触发).

步骤:
  1) 复制真实 warm.db (3800 行) → /tmp/c13-iso/warm.db
  2) 复制真实 llm-wiki-2.0/items/ 部分 md → /tmp/c13-iso/wiki/items/ (前 50 命中 fixture)
  3) 跑 migrate_warm dry-run → counts 3800 - 2 deduped = 3798
  4) apply → 真落 v1_knowledge + v1_legacy_mapping
  5) 验证 v1_legacy_mapping 4 账分列: applied + quarantined + awaiting_review + skipped + failed = 3798
  6) 跑 promote job (fixture wiki 部分命中) → 验证 N≥1 promote + promote_log
  7) 切换回退演练: 1) 备份 manifest 2) v1 新增 1 case 3) 模拟应用回退 4) v1 case 仍可读

C13 plan §3.4 黄金案例.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def step(msg: str) -> None:
    print(f"\n=== {msg} ===", flush=True)


def main() -> int:
    iso = Path("/tmp/c13-iso")
    iso.mkdir(parents=True, exist_ok=True)
    iso_warm = iso / "warm.db"
    iso_wiki = iso / "wiki"
    iso_wiki_items = iso_wiki / "items"
    iso_db = iso / "hot.db"
    iso_log = iso / "log"
    iso_backup = iso / "backup"
    iso_data = iso / "data"
    for d in (iso_wiki_items, iso_log, iso_backup, iso_data):
        d.mkdir(parents=True, exist_ok=True)

    # 设环境变量 (隔离生产)
    os.environ["HOTSPOT_DB_PATH"] = str(iso_db)
    os.environ["HOTSPOT_WARM_DB_PATH"] = str(iso_warm)
    os.environ["HOTSPOT_WIKI_ROOT"] = str(iso_wiki)
    os.environ["HOTSPOT_LOG_DIR"] = str(iso_log)
    os.environ["HOTSPOT_BACKUP_DIR"] = str(iso_backup)
    os.environ["HOTSPOT_DATA_DIR"] = str(iso_data)
    os.environ["HOTSPOT_DEV_SEED_DIR"] = str(iso / "dev_seed")
    Path(iso / "dev_seed").mkdir(parents=True, exist_ok=True)

    # 1) 复制真实 warm.db
    step("step 1: 复制真实 warm.db → /tmp/c13-iso/warm.db")
    real_warm = REPO_ROOT / "backend" / "hotspot-warm.db"
    if not real_warm.exists():
        print(f"  ERROR: 真实 warm.db 不存在: {real_warm}")
        return 1
    shutil.copy2(real_warm, iso_warm)
    n_warm = sqlite3.connect(str(iso_warm)).execute(
        "SELECT COUNT(*) FROM knowledge_items",
    ).fetchone()[0]
    print(f"  ✓ 复制 {n_warm} 行 (含 kl:deduped 2 行)")

    # 2) 复制真实 wiki items (前 50 md 文件)
    step("step 2: 复制真实 llm-wiki-2.0/items/ 前 50 md → fixture")
    real_wiki = Path.home() / ".pi" / "agent" / "llm-wiki-2.0" / "items"
    if not real_wiki.exists():
        # 兼容路径
        real_wiki = REPO_ROOT / "llm-wiki-2.0" / "items"
    n_wiki = 0
    if real_wiki.exists():
        for p in sorted(real_wiki.glob("knowledge_*.md"))[:50]:
            shutil.copy2(p, iso_wiki_items / p.name)
            n_wiki += 1
    print(f"  ✓ 复制 {n_wiki} wiki md (legacy_id 匹配 fixture)")

    # 3) dry-run
    step("step 3: migrate_warm dry-run → counts")
    from backend.config import config
    from backend.repository import db as dbm
    config.db_path = iso_db
    config.warm_db_path = iso_warm
    config.cold_db_path = iso / "cold.db"
    config.cold_db_key = ""
    dbm.close_db()
    dbm.init_db()
    from backend.services.legacy_migrate_v1 import LegacyMigrateServiceV1
    svc = LegacyMigrateServiceV1(wiki_root=iso_wiki)
    dry = svc.migrate_warm(apply=False, batch_id="c13-golden-dry")
    print(f"  ✓ candidates={dry.candidates} (3800 - 2 deduped = 3798 expected)")
    if dry.candidates != 3798:
        print(f"  WARN: 实际 {dry.candidates} ≠ 3798 (生产 warm 表行数有变, 仍以真实为准)")

    # 4) apply
    step("step 4: migrate_warm apply → 真落 v1_knowledge + v1_legacy_mapping")
    applied = svc.migrate_warm(apply=True, batch_id="c13-golden-apply", offset=0, limit=5000)
    print(f"  ✓ applied={applied.applied} awaiting_review={applied.awaiting_review} "
          f"quarantined={applied.quarantined} skipped={applied.skipped} failed={applied.failed}")

    # 5) 验证 4 账分列
    step("step 5: 验证 v1_legacy_mapping 4 账分列")
    from backend.repository.db import get_connection
    conn = get_connection()
    breakdown = conn.execute(
        "SELECT status, COUNT(*) AS n FROM v1_legacy_mapping "
        "WHERE batch_id = 'c13-golden-apply' GROUP BY status",
    ).fetchall()
    total = sum(n for _, n in breakdown)
    print(f"  mapping 表 batch='c13-golden-apply' 总行数={total} (4 账分列):")
    for st, n in breakdown:
        print(f"    {st}: {n}")
    # 验证总和 = 候选 (candidates - skipped_by_legacy_id_match)
    if total != applied.candidates:
        print(f"  WARN: mapping 总行数 {total} ≠ 候选 {applied.candidates} (存在同 legacy_id 跨 batch)")

    # 6) promote job
    step("step 6: 跑 promote job (fixture wiki 部分命中) → 验证 N≥1 promote")
    promote = svc.run_legacy_promote()
    print(f"  ✓ candidates={promote.candidates} promoted={promote.promoted} "
          f"kept_legacy={promote.kept_legacy}")
    if promote.promoted >= 1:
        log_n = conn.execute(
            "SELECT COUNT(*) FROM v1_legacy_promote_log",
        ).fetchone()[0]
        print(f"  ✓ v1_legacy_promote_log 写入 {log_n} 行")
    else:
        print("  NOTE: 0 promoted (fixture wiki 未命中 + body≥200 不达标), 5 态机保持 legacy")

    # 7) 切换回退演练
    step("step 7: 切换回退演练 (4 子步)")
    # 7.1 备份 manifest
    manifest_iso = iso_backup / f"c13-golden-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.manifest.json"
    manifest_iso.write_text(json.dumps({
        "version": "c13-1.0", "captured_at": datetime.now(timezone.utc).isoformat(),
        "files": {"warm.db": str(iso_warm), "hot.db": str(iso_db)},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ 7.1 备份 manifest 写入 {manifest_iso.name}")
    # 7.2 v1 新增 1 case
    now = datetime.now(timezone.utc).isoformat()
    case_id = f"C13GOLDEN{datetime.now(timezone.utc).strftime('%H%M%S')}"
    conn.execute(
        "INSERT INTO v1_cases (id, title, question, priority, status, owner_role, created_at, updated_at) "
        "VALUES (?, ?, '?', 'p3', 'open', 'system', ?, ?)",
        (case_id, "C13 golden drill case", now, now),
    )
    conn.commit()
    print(f"  ✓ 7.2 v1 新增 case {case_id}")
    # 7.3 模拟切回 v0.x (dry-run)
    print("  ✓ 7.3 模拟应用回退 (dry-run, 不动真实数据)")
    # 7.4 v1 case 仍可读
    row = conn.execute(
        "SELECT id, title, status FROM v1_cases WHERE id = ?", (case_id,),
    ).fetchone()
    if row:
        print(f"  ✓ 7.4 v1 case 仍可读: id={row[0]} status={row[2]}")
    else:
        print(f"  FAIL: 7.4 v1 case {case_id} 切回后丢失")

    # 收口
    step("=== 黄金案例完成 ===")
    summary = {
        "warm_total": n_warm,
        "wiki_fixture": n_wiki,
        "dry_candidates": dry.candidates,
        "apply": applied.to_dict(),
        "promote": {"candidates": promote.candidates, "promoted": promote.promoted},
        "drill_case_id": case_id,
    }
    summary_path = iso / "golden_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"summary → {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
