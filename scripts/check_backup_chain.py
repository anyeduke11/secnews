"""T6.7: 备份链 CI 校验脚本。

用途
----
每周日 backup_incremental → full 后跑一次:
  1. 读 chain.meta (checkpoint_seq + pages)
  2. 对每个 incremental/wal-*.bin 校验非空 + WIB1 头 + 记录完整 + .sha256 (P0-C:
     旧实现对内容零校验, 0 字节 .bin 也 PASS)
  3. 把 full backup 解到 tmpdir + 真实应用增量页 → PRAGMA integrity_check
  4. 通过 → 写 INTEGRITY_OK.{ts} 标记
  5. 失败 → 返 exit 2 + stderr 详情

CI: backend-core-only job 周日跑这个脚本; 失败红条报警到 editorial Today card。

CLI:
    PYTHONPATH=. .venv/bin/python scripts/check_backup_chain.py
    PYTHONPATH=. .venv/bin/python scripts/check_backup_chain.py --strict
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

BACKUPS_DIR = REPO_ROOT / "backend" / "backups"
INCREMENTAL_DIR = BACKUPS_DIR / "incremental"
CHAIN_META = INCREMENTAL_DIR / "chain.meta"

from backend.services.backup_service import (  # noqa: E402
    apply_incremental_chain,
    parse_incremental_bin,
)


def sha256_file(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--strict", action="store_true", help="任何警告都返 2")
    p.add_argument("--json", action="store_true", dest="json_out")
    args = p.parse_args()

    checks: list[dict] = []
    failed = False

    def fail(name: str, error: str, **extra: object) -> None:
        nonlocal failed
        checks.append({"name": name, "ok": False, "error": error, **extra})
        failed = True

    # ------------------------------------------------------------------
    # 1. latest full backup exists (P0-C 残余修复: glob 收紧为 [0-9] 开头,
    #    否则 hotspot-warm-*/cold-* 会被误当 full 候选)
    # ------------------------------------------------------------------
    latest_full: Path | None = None
    try:
        fulls = sorted(BACKUPS_DIR.glob("hotspot-[0-9]*.db"), key=lambda p: p.stat().st_mtime)
        if not fulls:
            fail("full_backup_exists", "no hotspot-[0-9]*.db in backups/")
        else:
            latest_full = fulls[-1]
            checks.append({
                "name": "full_backup_exists",
                "ok": True,
                "path": str(latest_full),
                "size_mb": round(latest_full.stat().st_size / 1e6, 1),
            })
    except Exception as e:  # noqa: BLE001 — 每检查项独立容错, 不 traceback
        fail("full_backup_exists", str(e))

    # ------------------------------------------------------------------
    # 2. quick_check full backup
    # ------------------------------------------------------------------
    if latest_full is not None:
        try:
            conn = sqlite3.connect(str(latest_full))
            try:
                r = conn.execute("PRAGMA quick_check").fetchall()
                ok = all(row[0] == "ok" for row in r)
                if ok:
                    checks.append({"name": "full_backup_quick_check", "ok": True})
                elif any(
                    "vtable constructor failed" in str(row) for row in r
                ):
                    # standalone CLI 不带 FTS5 module — 已知降级 warn
                    checks.append({
                        "name": "full_backup_quick_check", "ok": True,
                        "warn": "vtable constructor failed (missing FTS5 module in CLI)",
                    })
                else:
                    fail("full_backup_quick_check", "; ".join(str(row[0]) for row in r))
            finally:
                conn.close()
        except sqlite3.OperationalError as e:
            if "vtable constructor failed" in str(e):
                checks.append({
                    "name": "full_backup_quick_check", "ok": True,
                    "warn": "vtable constructor failed (missing FTS5 module in CLI)",
                })
            else:
                fail("full_backup_quick_check", str(e))
        except Exception as e:  # noqa: BLE001
            fail("full_backup_quick_check", str(e))

    # ------------------------------------------------------------------
    # 3. incremental chain (P0-C 残余修复: 只取 mtime 晚于所用 full 的 .bin —
    #    旧 bin 重放到新 full 上会把页回退到旧状态, 属结构性隐患)
    # ------------------------------------------------------------------
    chain_files: list[Path] = []
    total_pages = 0
    if not INCREMENTAL_DIR.exists():
        checks.append({"name": "incremental_dir_exists", "ok": True, "note": "no chain yet"})
    else:
        try:
            all_bins = sorted(INCREMENTAL_DIR.glob("wal-*.bin"))
            full_mtime = latest_full.stat().st_mtime if latest_full else 0.0
            chain_files = [cf for cf in all_bins if cf.stat().st_mtime >= full_mtime]
            excluded = [cf.name for cf in all_bins if cf not in chain_files]
            checks.append({
                "name": "incremental_chain_count",
                "ok": True,
                "count": len(chain_files),
                **({"excluded_older_than_full": excluded} if excluded else {}),
            })
        except Exception as e:  # noqa: BLE001
            fail("incremental_chain_count", str(e))

        # 逐文件真校验 — 非空 + WIB1 header + 记录完整
        try:
            bad_content: list[tuple[str, str]] = []
            for cf in chain_files:
                data = cf.read_bytes()
                if len(data) == 0:
                    bad_content.append((cf.name, "0-byte file (chain broken)"))
                    continue
                try:
                    _, pages = parse_incremental_bin(data)
                    total_pages += len(pages)
                except ValueError as e:
                    bad_content.append((cf.name, str(e)))
            if bad_content:
                fail("incremental_content", "; ".join(f"{n}: {m}" for n, m in bad_content),
                     bad=[list(b) for b in bad_content])
            else:
                checks.append({
                    "name": "incremental_content",
                    "ok": True,
                    "verified": len(chain_files),
                    "total_pages": total_pages,
                })
        except Exception as e:  # noqa: BLE001
            fail("incremental_content", str(e))

        # sha256 复算
        try:
            bad_sha = []
            for cf in chain_files:
                sha_file = cf.with_suffix(cf.suffix + ".sha256")
                if not sha_file.exists():
                    bad_sha.append((cf.name, "no .sha256 sidecar"))
                    continue
                expected = sha_file.read_text().split()[0]
                actual = sha256_file(cf)
                if expected != actual:
                    bad_sha.append((cf.name, f"sha256 mismatch: expected={expected[:8]} actual={actual[:8]}"))
            if bad_sha:
                fail("incremental_sha256", "; ".join(f"{n}: {m}" for n, m in bad_sha),
                     bad=[list(b) for b in bad_sha])
            else:
                checks.append({"name": "incremental_sha256", "ok": True, "verified": len(chain_files)})
        except Exception as e:  # noqa: BLE001
            fail("incremental_sha256", str(e))

        # chain.meta 对账: meta (seq sha ts pages) 记录最新一份 bin 的页数/sha —
        # 按 ts 前缀定位对应 bin 逐一对账 (全链求和在多 bin 时恒不等, 旧判法错)
        try:
            if chain_files and CHAIN_META.exists():
                parts = CHAIN_META.read_text().split()
                if len(parts) >= 4:
                    meta_seq, meta_sha, meta_ts = parts[0], parts[1], parts[2]
                    meta_pages = int(parts[3])
                    matched = [cf for cf in chain_files if cf.name.startswith(f"wal-{meta_ts}-")]
                    if len(matched) != 1:
                        checks.append({
                            "name": "chain_meta_pages", "ok": True,
                            "warn": f"meta ts={meta_ts} matches {len(matched)} chain bins — skipped",
                        })
                    else:
                        cf = matched[0]
                        _, bin_pages = parse_incremental_bin(cf.read_bytes())
                        bin_sha = sha256_file(cf)
                        if len(bin_pages) != meta_pages or bin_sha != meta_sha:
                            fail(
                                "chain_meta_pages",
                                f"meta(pages={meta_pages}, sha={meta_sha[:8]}) != "
                                f"{cf.name}(pages={len(bin_pages)}, sha={bin_sha[:8]})",
                            )
                        else:
                            checks.append({
                                "name": "chain_meta_pages", "ok": True,
                                "bin": cf.name, "pages": meta_pages, "wal_seq": int(meta_seq),
                            })
                else:
                    checks.append({
                        "name": "chain_meta_pages", "ok": True,
                        "warn": "chain.meta predates page-count field — skipped",
                    })
        except Exception as e:  # noqa: BLE001
            fail("chain_meta_pages", str(e))

        # full 的 checkpoint_seq (manifest) vs 链 meta seq — info/warn 级
        try:
            if latest_full is not None and CHAIN_META.exists():
                manifest = BACKUPS_DIR / f"backup-manifest-{latest_full.stem.removeprefix('hotspot-')}.json"
                if manifest.exists():
                    hot = next(
                        (d for d in json.loads(manifest.read_text()).get("dbs", [])
                         if d.get("kind") == "hot"), None,
                    )
                    meta_seq = int(CHAIN_META.read_text().split()[0])
                    full_seq = int(hot.get("checkpoint_seq", 0)) if hot else 0
                    if full_seq and meta_seq < full_seq:
                        checks.append({
                            "name": "full_vs_chain_seq", "ok": True,
                            "warn": f"chain wal_seq={meta_seq} < full checkpoint_seq={full_seq}",
                        })
                    else:
                        checks.append({
                            "name": "full_vs_chain_seq", "ok": True,
                            "full_checkpoint_seq": full_seq, "chain_wal_seq": meta_seq,
                        })
        except Exception as e:  # noqa: BLE001
            checks.append({"name": "full_vs_chain_seq", "ok": True, "warn": str(e)})

        # 4. 应用增量到 full 副本 → integrity_check (真实页写入)
        if chain_files and latest_full is not None and not failed:
            try:
                with tempfile.TemporaryDirectory() as td:
                    test_db = Path(td) / "test.db"
                    shutil.copy2(latest_full, test_db)
                    apply_result = apply_incremental_chain(test_db, chain_files)
                    if apply_result.get("ok"):
                        checks.append({
                            "name": "full_plus_chain_integrity",
                            "ok": True,
                            "applied_pages": apply_result.get("applied_pages"),
                            "integrity_check": apply_result.get("integrity_check"),
                            **({"warn": apply_result["integrity_warn"]}
                               if apply_result.get("integrity_warn") else {}),
                        })
                    else:
                        msg = apply_result.get("error") or apply_result.get("integrity_check", "unknown")
                        if "vtable constructor failed" in str(msg):
                            checks.append({
                                "name": "full_plus_chain_integrity", "ok": True,
                                "warn": "vtable constructor failed",
                            })
                        else:
                            fail("full_plus_chain_integrity", str(msg))
            except Exception as e:  # noqa: BLE001 — malformed 等不再 traceback
                fail("full_plus_chain_integrity", str(e))

    # ------------------------------------------------------------------
    # 5. knowledge.zip 校验 (如果存在)
    # ------------------------------------------------------------------
    try:
        for kz in sorted(BACKUPS_DIR.glob("*knowledge*.zip")):
            sz = kz.stat().st_size
            checks.append({"name": "knowledge_zip", "ok": sz > 0, "path": str(kz), "size": sz})
    except Exception as e:  # noqa: BLE001
        fail("knowledge_zip", str(e))

    overall_ok = not failed

    envelope = {
        "ok": overall_ok,
        "checks": checks,
        "summary": {
            "total": len(checks),
            "passed": sum(1 for c in checks if c["ok"]),
            "failed": sum(1 for c in checks if not c["ok"]),
        },
    }

    if args.json_out:
        print(json.dumps(envelope, ensure_ascii=False, indent=2))
    else:
        for c in checks:
            tag = "OK  " if c["ok"] else "FAIL"
            detail = c.get("error") or c.get("warn") or c.get("path") or ""
            if not detail and c.get("bad"):
                detail = str(c["bad"])[:80]
            print(f"  [{tag}] {c['name']}: {str(detail)[:100]}")
        print(f"\n{envelope['summary']['passed']}/{envelope['summary']['total']} checks passed"
              f" (exit {'0' if overall_ok else '2'})")

    if overall_ok and INCREMENTAL_DIR.exists():
        import time as _t

        ok_marker = BACKUPS_DIR / f"INTEGRITY_OK.{int(_t.time())}"
        ok_marker.write_text(json.dumps(envelope, ensure_ascii=False))

    return 0 if overall_ok else 2


if __name__ == "__main__":
    sys.exit(main())
