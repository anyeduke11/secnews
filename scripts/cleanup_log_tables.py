#!/usr/bin/env python3
"""cleanup_log_tables.py — 日志类表环形截断 (v0.8.8 P2.5 C2.2 / R-17 §5)。

背景: ``job_runs`` 30 天 TTL 挡不住体积 — 实测 11,167 行/天 (≈465/小时),
30 天窗内仍留 190,407 行; ``admission_log`` 95.84 MB 单表占全库 27%。
R-17 把 SQLite 定位为「只存热数据」工作集 → 日志类必须**环形封顶**,
不能只靠时间窗。

截断口径 (owner 2026-11-12 裁决):
  job_runs       行数上限 20,000 + 存续 30 天 (对齐 /api/ops/runs hours 上界)
  admission_log  行数上限 15,000
  llm_usage_log  存续 30 天
  ai_scores      随 hotspots 同窗 (30 天) —— FK 已剥离 (migration 132),
                 热点下沉后须显式删, 否则悬空引用堆积
  wiki_events    行数上限 8,000, 但**保留全部 sink / rebuild / rebuild_diff 事件**
                 且**保留全部带 wiki_path / db_ref 的行** (反查端点
                 trace_by_wiki_path / trace_by_db_ref 无时间下界, 截断会丢追溯链)
                 ⚠️ 实测: 生产 wiki_events 29,857 行**全部**带 wiki_path →
                 可删集合为 0 → 该规则下 wiki_events 实际不截断 (语义安全优先)

设计要点:
  - **环形**: 删最旧行, 保留最新 N 行 (不是删超窗外的全部)
  - **dry-run 优先**: **默认 dry-run**, ``--execute`` 才真删 (cleanup_* 脚本
    硬约定: 破坏性脚本默认不写库)
  - **不手写 FTS DML**: 本脚本只删日志类表, 不触碰 hotspots FTS
  - **WAL 治理**: 删除后跑 ``PRAGMA wal_checkpoint(TRUNCATE)`` 回收 WAL;
    ``--vacuum`` 额外跑 VACUUM 回收文件空间 (auto_vacuum=0 → DELETE 只把页
    推入 freelist, 文件体积不变)
  - **fail-loud**: 单表失败不影响其余表; 失败计入 envelope 并影响退出码

用法:
  python scripts/cleanup_log_tables.py --dry-run --json     (默认)
  python scripts/cleanup_log_tables.py --execute --json
  python scripts/cleanup_log_tables.py --execute --vacuum --json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

EXIT_OK = 0
EXIT_PARTIAL = 1
EXIT_FATAL = 2

# 保留的 wiki_events kind — R-17 沉降/重建的审计链, 任何情况下不得删
WIKI_EVENT_KEEP_KINDS = ("sink", "rebuild", "rebuild_diff")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cutoff(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _trim_by_age(
    conn: sqlite3.Connection, table: str, ts_column: str, days: float
) -> int:
    """删掉 ts_column < cutoff 的行, 返回删除行数。"""
    cur = conn.execute(
        f"DELETE FROM {table} WHERE {ts_column} < ?", (_cutoff(days),)
    )
    return cur.rowcount


def _trim_by_count(
    conn: sqlite3.Connection, table: str, ts_column: str, keep: int
) -> int:
    """环形保留最新 keep 行 (按 ts_column DESC, id DESC 排序), 删其余最旧行。

    实现: 先算出「第 keep+1 新」的 (ts, id) 边界, 再用**行值比较**删比它旧的
    行 —— 单条 DELETE 完成, 不需先全表读出 id 列表 (job_runs 19 万行时
    逐行删极慢)。

    为什么用 (ts, id) 而非只比 ts: 同一时刻的并发写入会产生同 ts 的多行,
    只比 ts 会连带删掉边界行 → 实际行数 > keep (实测 20,001)。行值比较
    (SQLite ≥ 3.15 支持) 把 (ts, id) 当复合键比较, 边界精确 → 行数精确等于 keep。

    边界取「第 keep+1 新」且谓词用 ``<=``: 边界行本身也要删 (它排在保留的
    keep 行之外), 用 ``<`` 会多留一行 (实测 20,001)。

    前置约束: ts 列必须 NOT NULL (行值比较遇 NULL 结果为 NULL → 行不删)。
    生产 5 张表的 ts 列均为 NOT NULL 且无 NULL 行 (已核验)。
    """
    total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    if total <= keep:
        return 0
    boundary = conn.execute(
        f"SELECT {ts_column}, id FROM {table} ORDER BY {ts_column} DESC, id DESC "
        f"LIMIT 1 OFFSET ?",
        (keep,),
    ).fetchone()
    if boundary is None:
        return 0
    cur = conn.execute(
        f"DELETE FROM {table} WHERE ({ts_column}, id) <= (?, ?)", (boundary[0], boundary[1])
    )
    return cur.rowcount


def _trim_wiki_events(conn: sqlite3.Connection, keep: int) -> int:
    """wiki_events 环形截断 —— 双重保留规则。

    1. **kind 保留**: ``sink`` / ``rebuild`` / ``rebuild_diff`` 永不删
       (R-17 沉降/重建的审计链, 是「可重建」承诺的凭据)
    2. **引用保留**: 带 ``wiki_path`` 或 ``db_table``+``db_row_id`` 的行永不删
       (trace_by_wiki_path / trace_by_db_ref 反查端点无时间下界, 删了会丢
       「这条知识是哪次采集/哪个 agent 产生的」追溯链)
    """
    total = conn.execute("SELECT COUNT(*) FROM wiki_events").fetchone()[0]
    if total <= keep:
        return 0
    # 只在「可删集合」内做环形: 可删 = 非保留 kind 且无引用
    deletable = (
        f"(kind NOT IN ({','.join('?' * len(WIKI_EVENT_KEEP_KINDS))})) "
        f"AND COALESCE(wiki_path, '') = '' "
        f"AND COALESCE(db_table, '') = ''"
    )
    params = list(WIKI_EVENT_KEEP_KINDS)
    n_del = conn.execute(
        f"SELECT COUNT(*) FROM wiki_events WHERE {deletable}", params
    ).fetchone()[0]
    if n_del == 0:
        return 0
    if n_del <= keep:
        return 0
    # 可删集合内保留最新 keep 行 → 边界取「可删集合第 keep+1 新」的 (ts, id)
    # 行值比较 (SQLite ≥ 3.15) → 边界精确, 同 ts 并发行不被连带删
    boundary = conn.execute(
        f"SELECT ts, id FROM wiki_events WHERE {deletable} "
        f"ORDER BY ts DESC, id DESC LIMIT 1 OFFSET ?",
        (*params, keep),
    ).fetchone()
    if boundary is None:
        return 0
    cur = conn.execute(
        f"DELETE FROM wiki_events WHERE {deletable} AND (ts, id) <= (?, ?)",
        (*params, boundary[0], boundary[1]),
    )
    return cur.rowcount


def _record_wal(
    results: list[dict], conn: sqlite3.Connection, sql: str, label: str
) -> None:
    """跑一条 WAL 治理语句并把结果记进 envelope (成功也记录 → 步骤可核验)。"""
    try:
        conn.execute(sql)
        results.append({"table": label, "ok": True, "deleted": 0})
    except sqlite3.Error as e:
        results.append(
            {
                "table": label,
                "ok": False,
                "deleted": 0,
                "error": f"{type(e).__name__}: {e}",
            }
        )


def trim_all(db_path: Path, *, dry_run: bool, vacuum: bool = False) -> dict:
    """执行一轮截断, 返回 JSON-ready envelope。"""
    started = datetime.now(timezone.utc)
    if not db_path.exists():
        return {
            "ok": False,
            "code": EXIT_FATAL,
            "started_at": started.isoformat(),
            "duration_ms": 0,
            "data": {
                "error": f"db not found: {db_path}",
                "db": str(db_path),
                "dry_run": dry_run,
                "results": [],
            },
        }

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        conn.execute("PRAGMA busy_timeout = 30000")
        results = []

        def _record(table: str, fn) -> None:
            try:
                n = fn()
                results.append({"table": table, "ok": True, "deleted": n})
            except sqlite3.Error as e:
                results.append(
                    {"table": table, "ok": False, "deleted": 0, "error": f"{type(e).__name__}: {e}"}
                )

        # job_runs: 行数上限 20,000 + 存续 30 天 (双阈值, 取并集)
        _record(
            "job_runs",
            lambda: _trim_by_count(conn, "job_runs", "started_at", 20_000)
            + _trim_by_age(conn, "job_runs", "started_at", 30),
        )
        # admission_log: 行数上限 15,000
        _record(
            "admission_log",
            lambda: _trim_by_count(conn, "admission_log", "created_at", 15_000),
        )
        # llm_usage_log: 存续 30 天
        _record(
            "llm_usage_log",
            lambda: _trim_by_age(conn, "llm_usage_log", "occurred_at", 30),
        )
        # wiki_events: 行数上限 8,000 + 保留 sink/rebuild 与引用行
        _record("wiki_events", lambda: _trim_wiki_events(conn, 8_000))
        # ai_scores: 随 hotspots 同窗 (30 天) —— FK 已剥离 (migration 132),
        # 热点下沉后须显式删, 否则悬空引用堆积
        _record(
            "ai_scores",
            lambda: _trim_by_age(conn, "ai_scores", "scored_at", 30),
        )

        if not dry_run:
            conn.commit()
            # WAL 治理 (1/2): 删行不回收文件空间 (auto_vacuum=0) → 显式 checkpoint
            # 回收 WAL; 完整空间回收需 VACUUM (见下)
            _record_wal(
                results, conn, "PRAGMA wal_checkpoint(TRUNCATE)", "<wal_checkpoint>"
            )
            # VACUUM 回收文件空间: auto_vacuum=0 下 DELETE 只把页推入 freelist,
            # 文件体积不变 → 必须显式 VACUUM。实测 363MB 库 2.3s (macOS)。
            # VACUUM 需独占写锁, 生产运行时可能与在途事务冲突 → 失败仅告警,
            # 不影响截断结果 (截断本身已 commit, 空间回收可下次再试)。
            if vacuum:
                try:
                    conn.isolation_level = None  # 退出事务, 避免 VACUUM 报错
                    conn.execute("VACUUM")
                except sqlite3.Error as e:
                    results.append(
                        {
                            "table": "<vacuum>",
                            "ok": False,
                            "deleted": 0,
                            "error": f"{type(e).__name__}: {e}",
                        }
                    )
                # WAL 治理 (2/2): **VACUUM 之后必须再 checkpoint 一次**。
                # WAL 模式下 VACUUM 把整个重建后的库写进 WAL (≈ 库体积),
                # 而服务侧连接的自动 checkpoint 是 PASSIVE —— 只回写页,
                # **不截断 WAL 文件** → WAL 永久停在满尺寸。
                # 实测 (2026-11-12 生产): 截断后 db 199 MB + wal 210 MB = 399 MB,
                # **反而大于截断前的 364 MB** —— 净收益为负。
                # TRUNCATE 模式 checkpoint 会把 WAL 内容回写主库并把文件截到 0。
                _record_wal(
                    results, conn, "PRAGMA wal_checkpoint(TRUNCATE)", "<wal_checkpoint_after_vacuum>"
                )
        else:
            conn.rollback()

        failed = [r for r in results if not r["ok"]]
        deleted = sum(r["deleted"] for r in results)
        return {
            "ok": not failed,
            "code": EXIT_PARTIAL if failed else EXIT_OK,
            "started_at": started.isoformat(),
            "duration_ms": int((datetime.now(timezone.utc) - started).total_seconds() * 1000),
            "data": {
                "db": str(db_path),
                "dry_run": dry_run,
                "results": results,
                "deleted_total": deleted,
                "failed_tables": [r["table"] for r in failed],
            },
        }
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--db", default=None, help="目标 db 路径 (默认 config.db_path)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="只预览不删除 (默认)",
    )
    parser.add_argument("--execute", dest="dry_run", action="store_false", help="真实删除")
    parser.add_argument(
        "--vacuum",
        action="store_true",
        help="截断后跑 VACUUM 回收文件空间 (auto_vacuum=0 下删行不释放空间)",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON envelope")
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else None
    if db_path is None:
        from backend.config import config

        db_path = config.db_path

    envelope = trim_all(db_path, dry_run=args.dry_run, vacuum=args.vacuum)
    if args.json:
        print(json.dumps(envelope, ensure_ascii=False, indent=2, default=str))
    else:
        d = envelope["data"]
        mode = "DRY-RUN" if d.get("dry_run") else "EXECUTE"
        print(f"[trim] {mode} db={d.get('db')}")
        for r in d.get("results", []):
            status = "ok" if r["ok"] else f"FAIL {r.get('error')}"
            print(f"   {r['table']:16} deleted={r['deleted']:>7}  {status}")
        print(f"[trim] total deleted={d.get('deleted_total')}")
    return int(envelope["code"])


if __name__ == "__main__":
    raise SystemExit(main())
