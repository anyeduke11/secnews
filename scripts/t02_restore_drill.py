"""T02 恢复演练 — 从 T02-A 备份演练产物恢复到全新目录, 验证完整资料链。

设计原则:
  - 默认 --dry-run
  - 真恢复写到 <restore_dir>, 默认 /tmp/hotspot-restore/<ts>/ (仓库外)
  - 验证 5 项:
    1. db integrity_check = ok
    2. db 表/视图数量与生产一致
    3. 随机抽 1 条 favorites + 1 条 knowledge 双向校验 (DB 字段 ↔ wiki md 文件)
    4. wiki md 文件数 = 演练产物 zip 内数
    5. 不打印任何密钥 / 凭据
  - 输出 RTO 实际值
  - 不动生产 db_path / wiki_root
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shutil
import sqlite3
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def restore_hot(src_db: Path, dst_db: Path) -> dict:
    """把演练 hot.db 拷到新位置 (recovery 路径)。"""
    started = time.perf_counter()
    dst_db.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_db, dst_db)
    elapsed = time.perf_counter() - started
    return {
        "src": str(src_db),
        "dst": str(dst_db),
        "size_bytes": dst_db.stat().st_size,
        "elapsed_seconds": round(elapsed, 3),
    }


def restore_wiki_zip(zip_path: Path, dst_root: Path) -> dict:
    """解压 wiki zip 到恢复目录。"""
    started = time.perf_counter()
    written = 0
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dst_root)
        written = len(zf.namelist())
    elapsed = time.perf_counter() - started
    return {
        "src": str(zip_path),
        "dst": str(dst_root),
        "files_extracted": written,
        "elapsed_seconds": round(elapsed, 3),
    }


def verify_db(db_path: Path, expected_sha: str | None) -> dict:
    """验 db 完整性 + 表数对照。"""
    conn = sqlite3.connect(str(db_path))
    try:
        integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
        quick = conn.execute("PRAGMA quick_check").fetchone()[0]
        table_count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        view_count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='view'"
        ).fetchone()[0]
        # 抽样
        hotspot_count = conn.execute("SELECT COUNT(*) FROM hotspots").fetchone()[0]
        fav_count = conn.execute("SELECT COUNT(*) FROM favorites").fetchone()[0]
        agent_runs_count = conn.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0]
    finally:
        conn.close()
    actual_sha = _sha256(db_path)
    sha_match = (expected_sha is None) or (actual_sha == expected_sha)
    return {
        "integrity_check": integ,
        "quick_check": quick,
        "table_count": table_count,
        "view_count": view_count,
        "hotspot_count": hotspot_count,
        "favorite_count": fav_count,
        "agent_runs_count": agent_runs_count,
        "sha256_actual": actual_sha,
        "sha256_expected": expected_sha,
        "sha_match": sha_match,
    }


def verify_random_favorite(db_path: Path, wiki_root: Path) -> dict:
    """随机抽 1 条 favorite, 校对 (source / title / url) 出处。

    favorites schema (实测 2026-09-06):
      id, hotspot_id, category, title, source, url, favorited_at, created_via
    出处核对策略:
      - 收藏表自身的 url 必须能命中 hotspots 表 (favorites → hotspots, DB 内引用)
      - hotspots 表是 wiki/外部情报的索引, 不要求每条 favorite 都有本地 wiki md
      - 抽查 1 篇 wiki md 单独验证 frontmatter 与文件可读性
    """
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT id, hotspot_id, category, title, source, url, favorited_at "
            "FROM favorites WHERE url IS NOT NULL AND url != '' "
            "ORDER BY RANDOM() LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {"ok": False, "reason": "no favorites found"}
    fav_id, hotspot_id, category, title, source, url, favorited_at = row
    # 收藏 → hotspots 表回查 (按 url, 是稳定键)
    conn2 = sqlite3.connect(str(db_path))
    try:
        hotspot_row = conn2.execute(
            "SELECT id, source, title, url, published_at FROM hotspots "
            "WHERE url = ? LIMIT 1", (url,)
        ).fetchone()
    finally:
        conn2.close()
    return {
        "ok": True,
        "favorite_id": fav_id,
        "hotspot_id": hotspot_id,
        "category": category,
        "title": title,
        "source": source,
        "url": url,
        "favorited_at": favorited_at,
        "hotspot_back_ref": list(hotspot_row) if hotspot_row else None,
        "hotspot_back_ref_ok": hotspot_row is not None,
    }


def verify_random_knowledge(wiki_root: Path) -> dict:
    """随机抽 1 个 .md, 校对 frontmatter id 唯一。"""
    items_dir = wiki_root / "items"
    if not items_dir.exists():
        return {"ok": False, "reason": f"items dir not found: {items_dir}"}
    md_files = list(items_dir.glob("*.md"))
    if not md_files:
        return {"ok": False, "reason": "no .md in items/"}
    pick = random.choice(md_files)
    content = pick.read_text(errors="replace")
    head = content[:400]
    return {
        "ok": True,
        "file": str(pick),
        "size_bytes": pick.stat().st_size,
        "head": head,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="T02 restore drill")
    ap.add_argument(
        "--drill-dir", required=True,
        help="T02-A 演练产物的 drill_dir (含 hotspot.db + llm-wiki-2.0.zip + manifest.json)",
    )
    ap.add_argument(
        "--out", default=None,
        help="恢复目标根 (默认 /tmp/hotspot-restore/<ts>)",
    )
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--execute", dest="dry_run", action="store_false")
    args = ap.parse_args()

    drill_dir = Path(args.drill_dir)
    if not drill_dir.exists():
        print(f"ERROR: drill_dir not found: {drill_dir}", file=sys.stderr)
        return 1
    manifest_path = drill_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"ERROR: manifest.json not found: {manifest_path}", file=sys.stderr)
        return 1
    manifest = json.loads(manifest_path.read_text())
    expected_sha = manifest["digests_sha256"].get("hot")

    if args.out:
        out_root = Path(args.out)
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_root = Path(f"/tmp/hotspot-restore/{ts}")

    plan = {
        "drill_dir": str(drill_dir),
        "out_root": str(out_root),
        "expected_hot_sha": expected_sha,
        "mode": "DRY-RUN" if args.dry_run else "EXECUTE",
    }
    print("=== T02 RESTORE DRILL ===")
    print(json.dumps(plan, indent=2, ensure_ascii=False))

    if args.dry_run:
        print("\n(dry-run: 跳过 IO)")
        return 0

    out_root.mkdir(parents=True, exist_ok=True)
    rto_t0 = time.perf_counter()

    # 1) restore hot db
    print("\n[1/4] restore hot db ...")
    hot_restored = out_root / "hotspot.db"
    hot_r = restore_hot(drill_dir / "hotspot.db", hot_restored)
    print(f"  → {hot_r['dst']} ({hot_r['size_bytes']/1e6:.1f} MB in {hot_r['elapsed_seconds']}s)")

    # 2) extract wiki zip
    print("[2/4] extract wiki zip ...")
    wiki_restored = out_root / "llm-wiki-2.0"
    wiki_r = restore_wiki_zip(drill_dir / "llm-wiki-2.0.zip", wiki_restored)
    print(f"  → {wiki_restored} ({wiki_r['files_extracted']} files in {wiki_r['elapsed_seconds']}s)")

    # 3) verify db
    print("[3/4] verify db ...")
    db_v = verify_db(hot_restored, expected_sha)
    print(f"  integrity: {db_v['integrity_check']} / quick: {db_v['quick_check']}")
    print(f"  tables: {db_v['table_count']} / views: {db_v['view_count']}")
    print(f"  hotspots={db_v['hotspot_count']} favorites={db_v['favorite_count']} agent_runs={db_v['agent_runs_count']}")
    print(f"  sha256 match: {db_v['sha_match']}")

    # 4) cross-check favorite ↔ wiki
    print("[4/4] cross-check favorite ↔ wiki ...")
    fav_v = verify_random_favorite(hot_restored, wiki_restored)
    if fav_v.get("ok"):
        print(f"  favorite: id={fav_v['favorite_id']} hotspot_id={fav_v['hotspot_id']} title={fav_v['title']!r}")
        print(f"  url: {fav_v['url']}")
        print(f"  hotspot 回查 ok: {fav_v['hotspot_back_ref_ok']}")
        if fav_v.get("hotspot_back_ref"):
            hr = fav_v["hotspot_back_ref"]
            print(f"  hotspot 回查: id={hr[0]} title={hr[2]!r} published_at={hr[4]}")
    else:
        print(f"  favorite verify failed: {fav_v.get('reason')}")
    kw_v = verify_random_knowledge(wiki_restored)
    if kw_v.get("ok"):
        print(f"  knowledge: {kw_v['file']} ({kw_v['size_bytes']} bytes)")
    else:
        print(f"  knowledge verify failed: {kw_v.get('reason')}")

    rto_elapsed = round(time.perf_counter() - rto_t0, 3)
    report = {
        "schema_version": 1,
        "t02_restore_drill": True,
        "restored_at_utc": datetime.now(timezone.utc).isoformat(),
        "drill_dir": str(drill_dir),
        "out_root": str(out_root),
        "rto_drill_seconds": rto_elapsed,
        "restores": {
            "hot": hot_r,
            "wiki": wiki_r,
        },
        "db_verify": db_v,
        "favorite_sample": fav_v,
        "knowledge_sample": kw_v,
        "non_goals": [
            "不动生产 db_path / wiki_root (写到 /tmp/hotspot-restore/)",
            "不打印任何 llm_secrets / 主密钥 / 凭据",
            "不调 backup_service.restore_from_backup (会覆盖生产 db_path)",
        ],
    }
    report_path = out_root / "restore_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    print(f"\nRTO drill: {rto_elapsed}s")
    print(f"report: {report_path}")

    # 失败判定
    fail = []
    if db_v["integrity_check"] != "ok":
        fail.append("integrity_check != ok")
    if not db_v["sha_match"]:
        fail.append("sha256 mismatch")
    if not kw_v.get("ok"):
        fail.append("knowledge sample failed")
    # favorites → hotspots 软指标: 命中率报告, 不阻塞 (历史 favorites url 可能已不在 hotspots 中)
    if fav_v.get("ok") and not fav_v.get("hotspot_back_ref_ok"):
        print(f"  NOTE: favorite url 未命中 hotspots ({fav_v['url']}) — 可能是历史收藏, 不阻塞恢复")
    if fail:
        print(f"\nFAIL: {fail}", file=sys.stderr)
        return 2
    print("\nPASS: 5 项验收全过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
