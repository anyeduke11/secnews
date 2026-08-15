"""数据库自动备份 service — 每日快照 + 保留策略。

用 SQLite 的 **online backup API** (``Connection.backup``): 在 WAL 模式下
对运行中的服务安全 — 拷贝期间源库可继续读写, 得到一致性快照 (等价
``sqlite3 <db> ".backup <dst>"`` 的 Python 版)。

P4-8 (2026-08-16): 备份完整性 — 除 DB 快照外, 同时打包 ``knowledge/``
源文件 (知识库 .md 是本机真相源, 此前仅靠 git, 无独立备份/恢复流程)。
备份目录结构:
  backups/hotspot-{ts}.db              ← SQLite 快照
  backups/hotspot-{ts}.knowledge.zip   ← knowledge/ 源文件归档

保留策略: 默认保留最近 ``BACKUP_RETENTION`` (7) 份, 超龄自动删除。
备份目录: ``config.backup_dir`` (默认 ``backend/backups/``)。
"""
from __future__ import annotations

import shutil
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from backend.config import config
from backend.logging_config import logger

BACKUP_RETENTION = 7  # 保留最近 N 份
BACKUP_PREFIX = "hotspot-"


def _backup_knowledge(ts: str) -> Path | None:
    """打包 knowledge/ 源文件 (排除 .conflicts 与 __pycache__)。

    P4-8: 知识库 .md 是文件真相源, DB 只是读缓存 — 备份必须含源文件,
    否则恢复 DB 后知识条目正文仍会丢失。
    """
    from backend.services.knowledge_sync import KNOWLEDGE_DIR

    if not KNOWLEDGE_DIR.exists():
        return None
    dst = config.backup_dir / f"{BACKUP_PREFIX}{ts}.knowledge.zip"
    try:
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in KNOWLEDGE_DIR.rglob("*"):
                if not f.is_file():
                    continue
                rel = f.relative_to(KNOWLEDGE_DIR.parent)
                if ".conflicts" in rel.parts or "__pycache__" in rel.parts or ".DS_Store" in f.name:
                    continue
                zf.write(f, rel)
        logger.info(f"knowledge backup: {dst.name}")
        return dst
    except Exception as e:
        logger.warning(f"knowledge backup failed (non-fatal): {e}")
        return None


def restore_from_backup(db_file: Path, knowledge_zip: Path | None = None) -> dict:
    """P4-8: 恢复流程 — 从备份还原 DB (和可选 knowledge/ 源文件)。

    - DB: 复制备份 .db 覆盖当前 config.db_path (调用方需先停止服务)。
    - knowledge/: 解压 zip 到项目根 (保留相对路径)。

    返回 {"db": bool, "knowledge": bool, "paths": {...}}
    """
    result: dict = {"db": False, "knowledge": False, "paths": {}}
    if db_file.exists():
        dst = Path(config.db_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db_file, dst)
        result["db"] = True
        result["paths"]["db"] = str(dst)
    if knowledge_zip is not None and knowledge_zip.exists():
        from backend.services.knowledge_sync import KNOWLEDGE_DIR

        with zipfile.ZipFile(knowledge_zip, "r") as zf:
            zf.extractall(KNOWLEDGE_DIR.parent)
        result["knowledge"] = True
        result["paths"]["knowledge"] = str(KNOWLEDGE_DIR)
    logger.info(
        f"restore: db={result['db']} knowledge={result['knowledge']}"
    )
    return result


def backup_database() -> dict:
    """把当前 DB 快照到 backups/ 并清理超龄备份。

    P4-8: 同时打包 knowledge/ 源文件。

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

    # P4-8: knowledge/ 源文件归档
    _backup_knowledge(ts)

    # 保留策略: 按文件名排序保留最新 N 份 (db + knowledge.zip 同 ts 成对清理)
    all_backups = sorted(backups_dir.glob(f"{BACKUP_PREFIX}*"))
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


__all__ = ["BACKUP_RETENTION", "backup_database", "restore_from_backup"]
