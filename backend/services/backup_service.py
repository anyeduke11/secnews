"""数据库自动备份 service — 每日快照 + 保留策略。

用 SQLite 的 **online backup API** (``Connection.backup``): 在 WAL 模式下
对运行中的服务安全 — 拷贝期间源库可继续读写, 得到一致性快照 (等价
``sqlite3 <db> ".backup <dst>"`` 的 Python 版)。

保留策略: 默认保留最近 ``BACKUP_RETENTION`` (7) 份, 超龄自动删除。
备份目录: ``config.backup_dir`` (默认 ``backend/backups/``)。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from backend.config import config
from backend.logging_config import logger

BACKUP_RETENTION = 7  # 保留最近 N 份
BACKUP_PREFIX = "hotspot-"


def backup_database() -> dict:
    """把当前 DB 快照到 backups/ 并清理超龄备份。

    Returns:
        {"path": str, "size": int, "retained": int, "removed": int}
    """
    backups_dir: Path = config.backup_dir
    backups_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dst = backups_dir / f"{BACKUP_PREFIX}{ts}.db"

    src = Path(config.db_path)
    src_conn = sqlite3.connect(str(src))
    dst_conn = sqlite3.connect(str(dst))
    try:
        # online backup API — 源库可继续读写 (WAL 一致性快照)
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()

    # 保留策略: 按文件名排序保留最新 N 份
    all_backups = sorted(backups_dir.glob(f"{BACKUP_PREFIX}*.db"))
    stale = all_backups[:-BACKUP_RETENTION] if len(all_backups) > BACKUP_RETENTION else []
    removed = 0
    for f in stale:
        try:
            f.unlink(missing_ok=True)
            removed += 1
        except OSError as e:
            logger.warning(f"backup cleanup failed for {f.name}: {e}")

    size = dst.stat().st_size
    retained = len(all_backups) - removed
    logger.info(
        f"db backup: {dst.name} ({size / 1e6:.1f} MB), "
        f"retained={retained} removed={removed}"
    )
    return {"path": str(dst), "size": size, "retained": retained, "removed": removed}


__all__ = ["BACKUP_RETENTION", "backup_database"]
