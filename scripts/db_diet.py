"""M2-Task4: 表生命周期清理脚本 (db_diet)。

读取 ``scripts/retention.json`` 台账, 按声明执行 4 类操作:
- ``truncate``        原地 DELETE > N 天 (元数据可重生成)
- ``archive_db_table`` 移动到 _archive 表 (质量审计可追溯)
- ``archive_jsonl``  导出 JSONL 后 DELETE (无收藏的 hotspots)
- 跳过                  留作 dry_run 预览

设计要点
--------
- 复用 ``backend.services.maintenance_service`` 已有的清理函数, 避免重新实现
  (DRY): archive_quality_logs / cleanup_history / run_vacuum
- 干跑优先 (``--dry-run`` 默认 True) — 先在 .bak 副本演练再动实库
- 统一 CLI 契约 ``--json`` 输出 (SPEC §M2-Task5):
  ``{ok: bool, code: int, duration_ms: int, data: {...}}``
- 每张表单独 try/except 隔离, 失败不阻塞后续
- ``--vacuum-into`` 走 SQLite VACUUM INTO API 原子替换, 留 backup
- ``--backup-path`` 强制先在 .bak 副本演练, 演练通过再切换

用法
----
    # 1. 干跑预览 (默认, 不修改)
    PYTHONPATH=. .venv/bin/python scripts/db_diet.py --dry-run --json

    # 2. 实际执行 (指定备份路径, VACUUM INTO 演练)
    PYTHONPATH=. .venv/bin/python scripts/db_diet.py \\
        --execute --backup /tmp/hotspot.diet.bak --json

    # 3. 只清一张表 (调试)
    PYTHONPATH=. .venv/bin/python scripts/db_diet.py \\
        --execute --table quality_check_logs_archive --json
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# v0.5 M2-Task5: 统一 CLI 契约包装
from scripts.cli_contract import (
    EXIT_OK,
    EXIT_PARTIAL,
    EXIT_FATAL,
)

# ---------------------------------------------------------------------------
# 路径与常量
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "backend" / "hotspot.db"
RETENTION_PATH = REPO_ROOT / "scripts" / "retention.json"
BACKUPS_DIR = REPO_ROOT / "backend" / "backups"
ARCHIVE_DIR = REPO_ROOT / "backups" / "hotspots-archive"


# ---------------------------------------------------------------------------
# 台账加载
# ---------------------------------------------------------------------------
def load_retention(path: Path = RETENTION_PATH) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg.get("tables", [])


# ---------------------------------------------------------------------------
# 时间戳规整 (ts_format 兼容)
# ---------------------------------------------------------------------------
def _cutoff_iso(retention_days: int) -> str:
    """ISO 字符串 cutoff, 与 sqlite TEXT datetime 列比较。"""
    return (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()


# ---------------------------------------------------------------------------
# 备份 + VACUUM INTO 演练 (SPEC §1: 先在 .bak 副本演练)
# ---------------------------------------------------------------------------
def make_backup_snapshot(src: Path, dst: Path) -> dict[str, Any]:
    """拷贝源 db 到 dst (用 sqlite3 .backup 保证一致性, WAL 模式安全)。"""
    if not src.exists():
        return {"ok": False, "error": f"source db not found: {src}"}
    dst.parent.mkdir(parents=True, exist_ok=True)
    src_conn = sqlite3.connect(str(src))
    dst_conn = sqlite3.connect(str(dst))
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()
    return {
        "ok": True,
        "src": str(src),
        "dst": str(dst),
        "size": dst.stat().st_size,
    }


def vacuum_into(src: Path, dst: Path) -> dict[str, Any]:
    """VACUUM INTO: SQLite 3.27+ 原子压缩并写入新文件。

    与 backup() 不同, VACUUM INTO 重建文件 (减少碎片, 释放被删数据空间),
    适合在大量 DELETE 后使用。
    """
    if not src.exists():
        return {"ok": False, "error": f"source db not found: {src}"}
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    conn = sqlite3.connect(str(src))
    try:
        conn.execute(f"VACUUM INTO '{dst}'")
    finally:
        conn.close()
    return {
        "ok": True,
        "src": str(src),
        "dst": str(dst),
        "size_before": src.stat().st_size,
        "size_after": dst.stat().st_size,
    }


# ---------------------------------------------------------------------------
# 表清理调度器
# ---------------------------------------------------------------------------
def cleanup_table(
    conn: sqlite3.Connection,
    spec: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    """执行单张表的 retention 策略。失败隔离不抛。"""
    table = spec["table"]
    ts_col = spec["ts_column"]
    action = spec["action"]
    days = spec.get("retention_days")

    result: dict[str, Any] = {
        "table": table,
        "action": action,
        "retention_days": days,
        "dry_run": dry_run,
        "ok": False,
        "deleted": 0,
        "archived": 0,
        "skipped_reason": None,
    }

    # 校验: 表存在
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
    except Exception as e:
        result["skipped_reason"] = f"pragma_failed: {e}"
        return result
    if not exists:
        result["skipped_reason"] = "table_not_found"
        return result

    # 校验: retention_days 必填 (除非由外部系统管)
    if days is None:
        result["skipped_reason"] = "no_retention_days"
        return result

    cutoff = _cutoff_iso(days)

    try:
        if action == "truncate":
            # 直接 DELETE > cutoff
            row = conn.execute(
                f'SELECT COUNT(*) FROM "{table}" WHERE "{ts_col}" < ?',
                (cutoff,),
            ).fetchone()[0]
            if not dry_run and row > 0:
                conn.execute(
                    f'DELETE FROM "{table}" WHERE "{ts_col}" < ?',
                    (cutoff,),
                )
            result["deleted"] = row
            result["ok"] = True

        elif action == "archive_db_table":
            # 已有 _archive 表, 复用 maintenance_service.archive_quality_logs
            if table == "quality_check_logs":
                from backend.services.maintenance_service import archive_quality_logs

                r = archive_quality_logs(days=days, dry_run=dry_run)
                result["archived"] = r["rows_archived"]
                result["main_remaining"] = r["main_remaining"]
                result["archive_total"] = r["archive_total"]
                result["ok"] = True
            else:
                result["skipped_reason"] = f"archive_db_table not implemented for {table}"
                return result

        elif action == "archive_jsonl":
            # hotspots 180 天非收藏: 导出 JSONL + DELETE
            if table == "hotspots":
                archived = _archive_hotspots_jsonl(
                    conn, cutoff, ARCHIVE_DIR, dry_run=dry_run
                )
                result["archived"] = archived
                result["ok"] = True
            else:
                result["skipped_reason"] = f"archive_jsonl not implemented for {table}"
                return result
        else:
            result["skipped_reason"] = f"unknown_action: {action}"
            return result
    except Exception as e:
        result["skipped_reason"] = f"exception: {type(e).__name__}: {e}"
        return result

    return result


def _archive_hotspots_jsonl(
    conn: sqlite3.Connection,
    cutoff_iso: str,
    archive_dir: Path,
    dry_run: bool,
) -> int:
    """导出 180 天前非收藏 hotspots 到 JSONL, 然后 DELETE。

    收藏判断: NOT IN (SELECT hotspot_id FROM favorites)。
    收藏行永不删 (用户主动收藏 = 资产级)。
    """
    select_sql = (
        "SELECT COUNT(*) FROM hotspots "
        "WHERE ingested_at < ? "
        "AND id NOT IN (SELECT hotspot_id FROM favorites)"
    )
    if dry_run:
        return conn.execute(select_sql, (cutoff_iso,)).fetchone()[0]

    archive_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    jsonl_path = archive_dir / f"hotspots-{ts}.jsonl"

    rows = conn.execute(
        "SELECT id, title, url, source, category, published_at, score, "
        "quality_score, ingested_at, fetched_at, summary, region, bid_status "
        "FROM hotspots "
        "WHERE ingested_at < ? "
        "AND id NOT IN (SELECT hotspot_id FROM favorites)",
        (cutoff_iso,),
    ).fetchall()
    cols = ["id", "title", "url", "source", "category", "published_at", "score",
            "quality_score", "ingested_at", "fetched_at", "summary", "region", "bid_status"]
    archived = 0
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(dict(zip(cols, row)), ensure_ascii=False) + "\n")
            archived += 1

    if archived > 0:
        conn.execute(
            "DELETE FROM hotspots "
            "WHERE ingested_at < ? "
            "AND id NOT IN (SELECT hotspot_id FROM favorites)",
            (cutoff_iso,),
        )
    return archived


# ---------------------------------------------------------------------------
# Envelope 构造 (轻量纯函数版, 供 run() 内部使用)
# ---------------------------------------------------------------------------
def _make_envelope(
    ok: bool,
    data: dict[str, Any],
    started_at: float,
    code: int = 0,
) -> dict[str, Any]:
    """构造 envelope (不 emit, 由 main 决定 emit 与否)。

    shape 与 cli_contract.emit_envelope 一致, 但 cli_contract.emit_envelope
    是副作用版 (print + sys.exit), 这里用纯函数版便于 run() 复用。

    started_at 接受任意 float 时基 (time.time / time.monotonic 都行),
    自动选择时差更短的那个。
    """
    # 防呆: 如果 started_at > now (例如 caller 用了 monotonic, 这里用 time.time),
    # 退化为 duration_ms=0 而非负数。
    now_mono = time.monotonic()
    now_real = time.time()
    delta_real = now_real - started_at
    delta_mono = now_mono - started_at
    duration_ms = max(0, int(min(delta_real, delta_mono) * 1000))
    return {
        "ok": ok,
        "code": code,
        "duration_ms": duration_ms,
        "data": data,
    }


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    started_at = time.monotonic()
    if not DB_PATH.exists():
        return EXIT_FATAL, _make_envelope(
            ok=False, code=EXIT_FATAL, started_at=started_at,
            data={"error": f"db not found: {DB_PATH}"},
        )

    # M2-T6.4 反制: --execute + --vacuum-into + 服务在跑 → 拒绝, 防止 inode 漂移导致 corrupt
    if args.execute and not args.assume_down:
        try:
            import subprocess as _sp
            r = _sp.run(["lsof", str(DB_PATH)], capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                return EXIT_FATAL, _make_envelope(
                    ok=False, code=EXIT_FATAL, started_at=started_at,
                    data={
                        "error": f"db {DB_PATH} is held by another process; "
                                 "stop the service first or pass --assume-down",
                        "lsof_holders": [line.split()[1] for line in r.stdout.strip().splitlines()[1:]],
                    },
                )
        except FileNotFoundError:
            pass  # lsof 不可用 (linux without lsof), 跳过

    # 1) 加载台账
    try:
        retention = load_retention()
    except Exception as e:
        return EXIT_FATAL, _make_envelope(
            ok=False, code=EXIT_FATAL, started_at=started_at,
            data={"error": f"retention.json load failed: {e}"},
        )

    # 2) 过滤单表
    if args.table:
        retention = [r for r in retention if r["table"] == args.table]
        if not retention:
            return EXIT_FATAL, _make_envelope(
                ok=False, code=EXIT_FATAL, started_at=started_at,
                data={"error": f"table not in retention.json: {args.table}"},
            )

    # 3) 备份演练 (SPEC §1: 先在 .bak 副本演练)
    backup_result: dict[str, Any] = {"skipped": True}
    backup_path: Path | None = None
    if args.backup:
        backup_path = Path(args.backup)
        backup_result = make_backup_snapshot(DB_PATH, backup_path)
        if not backup_result["ok"]:
            return EXIT_FATAL, _make_envelope(
                ok=False, code=EXIT_FATAL, started_at=started_at,
                data={"error": "backup failed", "backup": backup_result},
            )
        # 在备份副本上跑干跑演练 (双保险, 不影响实库)
        if not args.execute:
            try:
                dry_conn = sqlite3.connect(str(backup_path))
                dry_results = [
                    cleanup_table(dry_conn, spec, dry_run=True)
                    for spec in retention
                ]
                dry_conn.close()
                backup_result["dry_run_on_backup"] = dry_results
            except Exception as e:
                backup_result["dry_run_failed"] = str(e)

    # 4) 实库执行 (--execute 才动)
    if args.execute:
        # 二次备份保险: 实操前再备份一次当前实库
        if backup_path is None:
            # safety 备份写到源库同目录 (mini_db 测试不污染共享 BACKUPS_DIR)
            safety_backup = DB_PATH.parent / f"{DB_PATH.stem}-diet-safety-{int(time.time())}.db"
            safety = make_backup_snapshot(DB_PATH, safety_backup)
            backup_result = {"safety_backup": safety}

    conn = sqlite3.connect(str(DB_PATH))
    try:
        results = []
        for spec in retention:
            results.append(cleanup_table(conn, spec, dry_run=not args.execute))
            if args.execute:
                # 每表一提交: 释放写锁。archive_db_table (quality_check_logs)
                # 内部经 maintenance_service.get_connection() 开第二连接,
                # 若主连接持有未提交事务会导致 database is locked。
                conn.commit()
    finally:
        conn.close()

    # 5) 评估整体状态
    failed = [r for r in results if not r["ok"] and not r.get("skipped_reason")]
    skipped = [r for r in results if r.get("skipped_reason") and not r["ok"]]
    success = [r for r in results if r["ok"]]
    exit_code = EXIT_PARTIAL if failed else EXIT_OK

    # 6) VACUUM INTO 收尾 (--execute + --vacuum-into)
    vacuum_result: dict[str, Any] = {"skipped": True}
    if args.execute and args.vacuum_into:
        tmp_vacuum = BACKUPS_DIR / f"hotspot-diet-vacuum-{int(time.time())}.db"
        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        vacuum_result = vacuum_into(DB_PATH, tmp_vacuum)
        if vacuum_result["ok"]:
            # 原子替换: 拷贝真空版到 hotspot.db
            try:
                shutil.copy2(tmp_vacuum, DB_PATH)
                vacuum_result["replaced"] = True
                vacuum_result["final_size"] = DB_PATH.stat().st_size
            except Exception as e:
                vacuum_result["replaced"] = False
                vacuum_result["replace_error"] = str(e)

    return exit_code, _make_envelope(
        ok=exit_code == EXIT_OK,
        code=exit_code,
        started_at=started_at,
        data={
            "db": str(DB_PATH),
            "db_size_before": DB_PATH.stat().st_size,
            "mode": "execute" if args.execute else "dry_run",
            "backup": backup_result,
            "vacuum_into": vacuum_result,
            "results": results,
            "summary": {
                "total": len(results),
                "succeeded": len(success),
                "failed": len(failed),
                "skipped": len(skipped),
                "rows_deleted": sum(r.get("deleted", 0) for r in results),
                "rows_archived": sum(r.get("archived", 0) for r in results),
            },
        },
    )


def main() -> int:
    p = argparse.ArgumentParser(description="M2-T4 db_diet — 按 retention.json 清理表")
    p.add_argument("--execute", action="store_true", help="实际执行 (默认干跑)")
    p.add_argument("--dry-run", action="store_true", default=True, help="只预览不修改 (默认)")
    p.add_argument("--backup", type=str, default=None, help="先备份到指定路径, 在备份副本上跑干跑演练")
    p.add_argument("--vacuum-into", action="store_true", help="execute 模式下, 走 VACUUM INTO 收尾")
    p.add_argument("--table", type=str, default=None, help="只清指定单表 (调试)")
    p.add_argument("--db-path", type=str, default=None,
                   help="覆盖默认 db 路径 (调试用; 通过 HOTSPOT_DB_PATH env 注入)")
    p.add_argument("--assume-down", action="store_true", default=True,
                   help="假设服务已停止 (单用户工位机默认; 跳过 lsof 锁检查)")
    p.add_argument("--check-live", action="store_true",
                   help="启用 lsof 锁检查, 若 hotspot.db 被持锁则拒绝执行 (与 --assume-down 互斥)")
    p.add_argument("--json", action="store_true", dest="json_out", help="输出 CLI 契约 JSON")
    args = p.parse_args()
    if args.execute:
        args.dry_run = False
    if args.check_live:
        args.assume_down = False

    # 注入自定义 db path: 同时改模块 DB_PATH 和 config.db_path
    # (config.db_path 是 backend.repository.db.get_connection() 用的,
    # 而 archive_quality_logs 等 service 函数走 config.db_path)
    if args.db_path:
        import os
        global DB_PATH
        DB_PATH = Path(args.db_path)
        os.environ["HOTSPOT_DB_PATH"] = args.db_path
        # monkeypatch config.db_path (必须在 import backend.services.* 之前)
        from backend.config import config as _cfg
        _cfg.db_path = DB_PATH
        # T6.4: 测试库 (mini_db) 没 warm.db/cold.db, 强制指向不存在的路径让 get_connection 跳过 ATTACH
        _cfg.warm_db_path = DB_PATH.parent / "nonexistent-warm.db"
        _cfg.cold_db_path = DB_PATH.parent / "nonexistent-cold.db"

    code, envelope = run(args)
    if args.json_out:
        print(json.dumps(envelope, ensure_ascii=False, indent=2))
    else:
        # 人类可读: 摘要 + 每表结果
        s = envelope["data"]["summary"]
        print(f"db_diet [{envelope['data']['mode']}] {envelope['duration_ms']}ms")
        print(f"  succeeded={s['succeeded']}/{s['total']}  "
              f"deleted={s['rows_deleted']:,}  archived={s['rows_archived']:,}")
        for r in envelope["data"]["results"]:
            tag = "OK" if r["ok"] else ("SKIP" if r.get("skipped_reason") else "FAIL")
            print(f"  [{tag:4s}] {r['table']:35s} {r['action']:18s} "
                  f"deleted={r.get('deleted', 0):>6,}  archived={r.get('archived', 0):>6,}  "
                  f"({r.get('skipped_reason') or ''})")
    return code


if __name__ == "__main__":
    sys.exit(main())