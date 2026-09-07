"""T02 备份演练脚本 — 独立于生产 backup_service, 输出到 _drill 子目录隔离。

设计原则 (EXECUTION_GUIDE §2 T02):
  - 默认 --dry-run (仅打印计划, 不真写)
  - 真演练需 --execute 显式
  - 不清生产 backup 目录, 不动 BACKUP_RETENTION 链
  - 演练产物在 <backup_dir>/_drill/<ts>/, 单独子目录, 不被生产 daily_db_backup 误清
  - 输出 manifest.json + integrity_check + RPO/RTO 实际值
  - 不打印任何密钥 / 凭据 / llm_secrets 主密钥

使用:
  python scripts/t02_backup_drill.py --dry-run         # 仅打印计划
  python scripts/t02_backup_drill.py --execute        # 真演练 (产生 _drill 目录)
  python scripts/t02_backup_drill.py --execute --db backend/hotspot.db --out backend/backups/_drill/custom
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# 允许 scripts/ 直接 import backend.*
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.config import config  # noqa: E402
from backend.wiki_fs.root import resolve_wiki_root  # noqa: E402


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _src_size(p: Path) -> int:
    return p.stat().st_size if p.exists() else 0


def plan(db_path: Path, warm_path: Path, cold_path: Path, wiki_root: Path, drill_dir: Path) -> dict:
    """dry-run 计划: 列出要备份的源, 不做任何 IO。"""
    wiki_files = list(wiki_root.rglob("*")) if wiki_root.exists() else []
    wiki_md = [f for f in wiki_files if f.is_file() and f.suffix.lower() in (".md", ".markdown")]
    wiki_other = [f for f in wiki_files if f.is_file() and f.suffix.lower() not in (".md", ".markdown")]
    return {
        "db": {
            "hot_path": str(db_path),
            "hot_size_bytes": _src_size(db_path),
            "warm_path": str(warm_path),
            "warm_size_bytes": _src_size(warm_path),
            "cold_path": str(cold_path),
            "cold_size_bytes": _src_size(cold_path),
        },
        "wiki": {
            "root": str(wiki_root),
            "total_files": sum(1 for f in wiki_files if f.is_file()),
            "md_files": len(wiki_md),
            "other_files": len(wiki_other),
        },
        "drill_dir": str(drill_dir),
    }


def backup_hot(src: Path, dst: Path) -> dict:
    """SQLite online backup API (WAL 一致性快照)。"""
    started = time.perf_counter()
    src_conn = sqlite3.connect(str(src))
    dst_conn = sqlite3.connect(str(dst))
    try:
        src_conn.backup(dst_conn)
        dst_conn.commit()
    finally:
        dst_conn.close()
        src_conn.close()
    elapsed = time.perf_counter() - started
    return {
        "dst": str(dst),
        "size_bytes": _src_size(dst),
        "elapsed_seconds": round(elapsed, 3),
        "throughput_mb_s": round(_src_size(dst) / 1e6 / max(elapsed, 1e-3), 1),
    }


def backup_simple_copy(src: Path, dst: Path) -> dict:
    """WARM/COLD 不走 SQLite backup API, 直接 copy (它们无并发写入)。

    v1.0 C01 R12 修复: 即便声明"无并发写入", ATTACH 跨 db 写入的
    knowledge_items 可能在 WAL 还没 checkpoint 时被读到, 副本丢行.
    改走 backup_with_api 走 SQLite backup API, 与 HOT 一致保 WAL 一致性.
    """
    return backup_with_api(src, dst)


def backup_with_api(src: Path, dst: Path) -> dict:
    """三库统一走 SQLite online backup API, 保 WAL 已 commit 未 checkpoint 行的副本完整."""
    started = time.perf_counter()
    src_conn = sqlite3.connect(str(src))
    dst_conn = sqlite3.connect(str(dst))
    try:
        src_conn.backup(dst_conn)
        dst_conn.commit()
    finally:
        dst_conn.close()
        src_conn.close()
    elapsed = time.perf_counter() - started
    return {
        "dst": str(dst),
        "size_bytes": _src_size(dst),
        "elapsed_seconds": round(elapsed, 3),
        "throughput_mb_s": round(_src_size(dst) / 1e6 / max(elapsed, 1e-3), 1),
    }


def snapshot_wiki(wiki_root: Path, zip_dst: Path) -> dict:
    """Wiki 快照: tar-less zip (排除 .conflicts / __pycache__ / .DS_Store)。"""
    started = time.perf_counter()
    skipped = []
    written = 0
    with zipfile.ZipFile(zip_dst, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in wiki_root.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(wiki_root)
            if ".conflicts" in rel.parts or "__pycache__" in rel.parts or f.name == ".DS_Store":
                skipped.append(str(rel))
                continue
            zf.write(f, rel)
            written += 1
    elapsed = time.perf_counter() - started
    return {
        "dst": str(zip_dst),
        "size_bytes": _src_size(zip_dst),
        "files_written": written,
        "files_skipped": len(skipped),
        "elapsed_seconds": round(elapsed, 3),
    }


def integrity_check(db_path: Path) -> dict:
    """对热备 db 跑 PRAGMA integrity_check。"""
    conn = sqlite3.connect(str(db_path))
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()
        quick = conn.execute("PRAGMA quick_check").fetchone()
        cnt = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
    finally:
        conn.close()
    return {
        "integrity_check": result[0] if result else "unknown",
        "quick_check": quick[0] if quick else "unknown",
        "table_count": cnt,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="T02 backup drill (default --dry-run)")
    ap.add_argument("--db", default=None, help="HOT db path (default: config.db_path)")
    ap.add_argument("--warm", default=None, help="WARM db path (default: config.warm_db_path)")
    ap.add_argument("--cold", default=None, help="COLD db path (default: config.cold_db_path)")
    ap.add_argument("--wiki", default=None, help="Wiki root (default: HOTSPOT_WIKI_ROOT or resolved)")
    ap.add_argument(
        "--out", default=None,
        help="Drill output dir (default: <backup_dir>/_drill/<UTC-ts>)",
    )
    ap.add_argument("--dry-run", action="store_true", default=True, help="Only plan (default)")
    ap.add_argument("--execute", dest="dry_run", action="store_false", help="Actually run")
    args = ap.parse_args()

    db_path = Path(args.db or config.db_path)
    warm_path = Path(args.warm or config.warm_db_path)
    cold_path = Path(args.cold or config.cold_db_path)
    wiki_root = Path(args.wiki or resolve_wiki_root())

    if args.out:
        drill_dir = Path(args.out)
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        drill_dir = Path(config.backup_dir) / "_drill" / ts

    plan_data = plan(db_path, warm_path, cold_path, wiki_root, drill_dir)
    print("=== T02 BACKUP DRILL ===")
    print(f"mode: {'DRY-RUN (plan only)' if args.dry_run else 'EXECUTE (will write)'}")
    print(f"drill_dir: {drill_dir}")
    print(json.dumps(plan_data, indent=2, ensure_ascii=False))

    if args.dry_run:
        print("\n(dry-run: 跳过实际 IO, 加 --execute 触发真演练)")
        return 0

    # ---- 真演练 ----
    if not db_path.exists():
        print(f"ERROR: HOT db not found: {db_path}", file=sys.stderr)
        return 1
    if not wiki_root.exists():
        print(f"ERROR: wiki root not found: {wiki_root}", file=sys.stderr)
        return 1

    drill_dir.mkdir(parents=True, exist_ok=True)
    rpo_start = time.time()  # 真实 RPO 起点 = 进入演练时刻
    rto_t0 = time.perf_counter()  # 恢复演练另算

    print("\n[1/4] backup HOT via online backup API ...")
    hot = backup_hot(db_path, drill_dir / "hotspot.db")
    print(f"  → {hot['dst']} ({hot['size_bytes']/1e6:.1f} MB in {hot['elapsed_seconds']}s, {hot['throughput_mb_s']} MB/s)")

    warm_result = None
    if warm_path.exists():
        print("[2/4] copy WARM ...")
        warm_result = backup_simple_copy(warm_path, drill_dir / "hotspot-warm.db")
        print(f"  → {warm_result['dst']} ({warm_result['size_bytes']/1e6:.1f} MB in {warm_result['elapsed_seconds']}s, {warm_result['throughput_mb_s']} MB/s)")
    else:
        print("[2/4] WARM not present, skip")

    cold_result = None
    if cold_path.exists():
        print("[3/4] copy COLD ...")
        cold_result = backup_simple_copy(cold_path, drill_dir / "hotspot-cold.db")
        print(f"  → {cold_result['dst']} ({cold_result['size_bytes']/1e3:.1f} KB in {cold_result['elapsed_seconds']}s)")
    else:
        print("[3/4] COLD not present, skip")

    print("[4/4] snapshot wiki ...")
    wiki_zip = drill_dir / "llm-wiki-2.0.zip"
    wiki = snapshot_wiki(wiki_root, wiki_zip)
    print(f"  → {wiki['dst']} ({wiki['files_written']} files, {wiki['size_bytes']/1e6:.1f} MB in {wiki['elapsed_seconds']}s)")

    # integrity check on hot backup
    print("\n[verify] PRAGMA integrity_check on hot backup ...")
    integ = integrity_check(drill_dir / "hotspot.db")
    print(f"  integrity_check: {integ['integrity_check']}")
    print(f"  quick_check: {integ['quick_check']}")
    print(f"  table_count: {integ['table_count']}")

    rpo_end = time.time()
    rpo_elapsed = round(rpo_end - rpo_start, 3)
    rto_drill_seconds = round(time.perf_counter() - rto_t0, 3)

    # sha256 摘要
    digests = {}
    for name, p in [
        ("hot", drill_dir / "hotspot.db"),
        ("warm", drill_dir / "hotspot-warm.db"),
        ("cold", drill_dir / "hotspot-cold.db"),
        ("wiki", drill_dir / "llm-wiki-2.0.zip"),
    ]:
        if p.exists():
            digests[name] = _sha256(p)

    manifest = {
        "schema_version": 1,
        "t02_drill": True,
        "drill_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "execute",
        "sources": {
            "db_hot": str(db_path),
            "db_warm": str(warm_path) if warm_path.exists() else None,
            "db_cold": str(cold_path) if cold_path.exists() else None,
            "wiki_root": str(wiki_root),
        },
        "artifacts": {
            "hot": hot,
            "warm": warm_result,
            "cold": cold_result,
            "wiki": wiki,
        },
        "integrity": integ,
        "rpo": {
            "started_at_epoch": rpo_start,
            "ended_at_epoch": rpo_end,
            "elapsed_seconds": rpo_elapsed,
            "note": "演练自身耗时不等于真实 RPO; 真 RPO = 上次备份以来丢失的写入窗口",
        },
        "rto_drill_seconds": rto_drill_seconds,
        "digests_sha256": digests,
        "drill_dir": str(drill_dir),
        "non_goals": [
            "不清生产 backup 目录 (BACKUP_RETENTION 链不动)",
            "不调 backup_service.backup_database() (会改 backup_dir 全局状态)",
            "不推送 WebDAV (HOTSPOT_REMOTE_BACKUP 默认空, 即便生产 hook 触发也只读 _maybe_remote_push)",
            "不打印任何 llm_secrets / 主密钥 / 凭据",
        ],
    }
    manifest_path = drill_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"\nmanifest: {manifest_path}")
    print(f"digests: {json.dumps(digests, indent=2)}")
    print(f"\nRPO drill elapsed: {rpo_elapsed}s / RTO drill elapsed: {rto_drill_seconds}s")
    print("(说明: RPO/RTO 演练值 = 演练自身耗时; 真 RPO = 上次 backup 至今窗口, 真 RTO = 灾难恢复演练总耗时, 需另测)")

    return 0 if integ["integrity_check"] == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
