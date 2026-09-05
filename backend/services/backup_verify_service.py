"""backup_verify — 备份完整性校验服务 (v0.8.2 Y-A4, CRITICAL_REVIEW §2.4)。

§2.4 原文推荐 "Fernet 解密 → 行数对比"; 实测备份为**明文** SQLite
(online backup API 直拷, Fernet 仅用于 cg_resources/secrets) — 因此
"解密"步骤不适用, 校验按明文库设计:

1. **PRAGMA integrity_check** — 备份文件自身页级损坏 (真实损坏探测器)
2. **核心表行数** — 备份 ≤ 实时 (采集单调增长; 备份比实时"多"= 恢复了
   错误文件/时间线混乱)
3. **append-only 抽样** — ``audit_log`` (id 幂等追加) 取备份尾部 10 行,
   按主键与实时库逐字段对比 (审计行不可变, 不一致 = 真实损坏;
   可变表行会被更新, md5 对比会产生假阳性, 不做)
4. **knowledge zip** — 伴随归档 ``zipfile.testzip()`` (无则跳过)

失败处置: 返回 ``ok=False`` 报告 + ``record_audit("backup_verify.failed")``
+ error 日志; 调度层 ``backup_verify_job`` 借 instrument_job 把失败标进
job 运行记录 (前端 job status / 告警链可见)。周一 02:00 (Asia/Shanghai)
由 ``backup_verify_job`` 触发 — 对齐 §2.4 推荐, 且在 04:30 daily backup
/ 周日 full 之后、业务低谷。
"""
from __future__ import annotations

import hashlib
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from backend.config import config
from backend.logging_config import logger

SAMPLE_ROWS = 10
CORE_TABLES = ("hotspots", "settings", "audit_log")
AUDIT_TABLE = "audit_log"


def _latest_backup() -> Path | None:
    """最新 full 备份 (排除 diet 残留); 无备份返回 None。"""
    backups_dir: Path = config.backup_dir
    if not backups_dir.exists():
        return None
    candidates = sorted(
        [
            f
            for f in backups_dir.glob("hotspot-*.db")
            if not f.name.startswith("hotspot-diet-")
        ],
        key=lambda p: p.stat().st_mtime,
    )
    return candidates[-1] if candidates else None


def _connect_ro(path: Path) -> sqlite3.Connection:
    """只读连接 (线程内构造 — SQLite 连接线程亲和纪律)。"""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in CORE_TABLES:
        try:
            counts[table] = conn.execute(
                f"SELECT count(*) AS n FROM {table}"
            ).fetchone()["n"]
        except sqlite3.OperationalError:
            counts[table] = -1  # 表不存在 (旧备份)
    return counts


def _row_digest(row: sqlite3.Row) -> str:
    payload = "\x1f".join(f"{k}\x1e{row[k]!r}" for k in row.keys())
    return hashlib.md5(payload.encode("utf-8", "surrogatepass")).hexdigest()


def _sample_append_only(
    backup_conn: sqlite3.Connection, live_conn: sqlite3.Connection
) -> dict:
    """audit_log 尾部 SAMPLE_ROWS 行逐字段对比 (append-only, 不可变)。"""
    try:
        rows = backup_conn.execute(
            f"SELECT * FROM {AUDIT_TABLE} ORDER BY id DESC LIMIT ?",
            (SAMPLE_ROWS,),
        ).fetchall()
    except sqlite3.OperationalError:
        return {"sampled": 0, "mismatched": 0, "skipped": "audit_log 不存在"}

    mismatched = 0
    for row in rows:
        live = live_conn.execute(
            f"SELECT * FROM {AUDIT_TABLE} WHERE id = ?",
            (row["id"],),
        ).fetchone()
        if live is None or _row_digest(row) != _row_digest(live):
            mismatched += 1
    return {"sampled": len(rows), "mismatched": mismatched}


def _verify_knowledge_zip(backup: Path) -> dict:
    """伴随 knowledge zip 完整性 (P4-8: .md 是文件真相源)。"""
    zp = backup.with_suffix(".knowledge.zip")
    if not zp.exists():
        return {"present": False, "ok": True, "path": str(zp)}
    try:
        with zipfile.ZipFile(zp) as zf:
            bad = zf.testzip()
        return {"present": True, "ok": bad is None, "path": str(zp), "bad_entry": bad}
    except (zipfile.BadZipFile, OSError) as exc:
        return {"present": True, "ok": False, "path": str(zp), "error": str(exc)}


def verify_latest_backup() -> dict:
    """校验最新 full 备份, 返回结构化报告 (永不抛 — 灾难检查自身不能炸)。"""
    started = datetime.now(timezone.utc)
    report: dict = {
        "ok": False,
        "checked_at": started.isoformat(),
        "backup_path": None,
        "errors": [],
    }
    try:
        backup = _latest_backup()
        if backup is None:
            report["errors"].append("未找到任何 full 备份 (backups/ 为空)")
            _finalize(report, started)
            return report
        report["backup_path"] = str(backup)

        backup_conn = _connect_ro(backup)
        live_conn = _connect_ro(Path(config.db_path))
        try:
            # 1) 页级完整性
            row = backup_conn.execute("PRAGMA integrity_check").fetchone()
            integrity = row[0] if row else "missing"
            report["integrity_check"] = integrity
            if integrity != "ok":
                report["errors"].append(f"integrity_check={integrity}")

            # 2) 行数单调性 (备份 ≤ 实时)
            backup_counts = _table_counts(backup_conn)
            live_counts = _table_counts(live_conn)
            report["tables"] = {
                t: {"backup": backup_counts[t], "live": live_counts[t]}
                for t in CORE_TABLES
            }
            for t in CORE_TABLES:
                if backup_counts[t] < 0 or live_counts[t] < 0:
                    continue  # 旧备份缺表, 跳过
                if backup_counts[t] > live_counts[t]:
                    report["errors"].append(
                        f"{t}: 备份 {backup_counts[t]} 行 > 实时 {live_counts[t]} 行"
                    )

            # 3) append-only 抽样
            report["audit_sample"] = _sample_append_only(backup_conn, live_conn)
            if report["audit_sample"].get("mismatched"):
                report["errors"].append(
                    f"audit_log 抽样 {report['audit_sample']['mismatched']} 行不一致"
                )
        finally:
            backup_conn.close()
            live_conn.close()

        # 4) knowledge zip
        report["knowledge_zip"] = _verify_knowledge_zip(backup)
        if not report["knowledge_zip"]["ok"]:
            report["errors"].append(
                "knowledge.zip 损坏: "
                f"{report['knowledge_zip'].get('bad_entry') or report['knowledge_zip'].get('error')}"
            )

        report["ok"] = not report["errors"]
        _finalize(report, started)
        if report["ok"]:
            logger.info(
                f"backup_verify: OK — {backup.name}, integrity=ok, "
                f"tables={ {t: v['backup'] for t, v in report['tables'].items()} }"
            )
        else:
            logger.error(f"backup_verify: FAILED — {report['errors']}")
            _audit_failure(report)
        return report
    except Exception as exc:
        report["errors"].append(f"verify crashed: {type(exc).__name__}: {exc}")
        _finalize(report, started)
        logger.error(f"backup_verify crashed: {exc}")
        _audit_failure(report)
        return report


def _finalize(report: dict, started: datetime) -> None:
    report["duration_ms"] = int(
        (datetime.now(timezone.utc) - started).total_seconds() * 1000
    )


def _audit_failure(report: dict) -> None:
    """失败留痕 audit_log (不抛 — 防御性)。"""
    try:
        from backend.observability_records import record_audit

        record_audit(
            actor="system",
            action="backup_verify.failed",
            target=report.get("backup_path") or "none",
            detail={"errors": report.get("errors", [])},
        )
    except Exception as exc:  # pragma: no cover - 防御性
        logger.warning(f"backup_verify audit failed (ignored): {exc}")
