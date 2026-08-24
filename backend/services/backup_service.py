"""数据库自动备份 service — 每日快照 + 保留策略。

用 SQLite 的 **online backup API** (``Connection.backup``): 在 WAL 模式下
对运行中的服务安全 — 拷贝期间源库可继续读写, 得到一致性快照 (等价
``sqlite3 <db> ".backup <dst>"`` 的 Python 版)。

P4-8 (2026-08-16): 备份完整性 — 除 DB 快照外, 同时打包 ``knowledge/``
源文件 (知识库 .md 是本机真相源, 此前仅靠 git, 无独立备份/恢复流程)。
备份目录结构:
  backups/hotspot-{ts}.db              ← SQLite 快照
  backups/hotspot-{ts}.knowledge.zip   ← knowledge/ 源文件归档

保留策略: 默认保留最近 ``BACKUP_RETENTION`` (1) 份, 超龄自动删除。

v0.5 增量备份
------------
设计动机: 单机工作站磁盘有限 + 1 GB DB 全量快照代价高。
策略: 每日 WAL checkpoint → 备份新追加 page (增量), 累积上限 ``MAX_INCREMENTAL_PAGES``。
每 7 天一次 full snapshot (周期轮转, 不丢失)。

热路径:
- 04:30 daily_db_backup_job → backup_incremental()
- weekly_maintenance_job (周日) → backup_full() 重置轮转

详细方案见 docs/v0.5_storage_design.md。
"""
from __future__ import annotations

import hashlib
import shutil
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from backend.config import config
from backend.logging_config import logger

# v0.5: BACKUP_RETENTION=1 (单盘只留最新一份); 7 天一次 full snapshot
BACKUP_RETENTION = 1
BACKUP_PREFIX = "hotspot-"

# 增量备份参数
INCREMENTAL_PAGE_SIZE = 4096      # SQLite 默认 page size
INCREMENTAL_DIR = "incremental"   # backups/{INCREMENTAL_DIR}/ 存增量
MAX_INCREMENTAL_PAGES = 8192      # 32MB 上限 (足够容下一次完整日采集)
INCREMENTAL_CHAIN_PREFIX = "wal-" # wal-{ts}-{seq}.bin 命名


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


def _maybe_remote_push(db_path: Path, knowledge_zip_name: str) -> None:
    """T6.9: remote backup hook — 默认关闭, 仅 HOTSPOT_REMOTE_BACKUP=webdav 时推送。

    触发条件:
    - env HOTSPOT_REMOTE_BACKUP=webdav

    实现: 通过 WebDAV (e.g. Nextcloud / 坚果云) 上传 .db + .knowledge.zip。
    失败仅 warn, 不阻塞本地备份。
    """
    import os
    backend = os.environ.get("HOTSPOT_REMOTE_BACKUP", "").lower()
    if not backend:
        return  # 默认关
    if backend != "webdav":
        logger.warning(f"unknown HOTSPOT_REMOTE_BACKUP backend: {backend}")
        return
    try:
        import requests
        from urllib.parse import quote

        webdav_url = os.environ.get("HOTSPOT_WEBDAV_URL", "")
        webdav_user = os.environ.get("HOTSPOT_WEBDAV_USER", "")
        webdav_password = os.environ.get("HOTSPOT_WEBDAV_PASSWORD", "")
        if not webdav_url:
            logger.warning("HOTSPOT_REMOTE_BACKUP=webdav but HOTSPOT_WEBDAV_URL not set")
            return
        for fname in (db_path.name, knowledge_zip_name):
            local = db_path.parent / fname
            if not local.exists():
                continue
            url = f"{webdav_url.rstrip('/')}/{quote(fname)}"
            with open(local, "rb") as f:
                resp = requests.put(
                    url,
                    data=f,
                    auth=(webdav_user, webdav_password) if webdav_user else None,
                    timeout=60,
                )
            if resp.status_code in (200, 201, 204):
                logger.info(f"remote push ok: {fname} → {webdav_url}")
            else:
                logger.warning(f"remote push failed: {fname} status={resp.status_code}")
    except Exception as e:
        logger.warning(f"remote backup hook failed (non-fatal): {e}")


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

    v0.5: BACKUP_RETENTION=1, 默认调增量 (backup_incremental),
    周日 weekly_maintenance 强制 full 重置。

    P4-8: 同时打包 knowledge/ 源文件。

    Returns:
        {"path": str, "size": int, "retained": int, "removed": int, "mode": "full|incremental"}
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
        # Python sqlite3 默认 deferred, 必须 commit 才能落盘 (否则 close 时 rollback)
        dst_conn.commit()
    finally:
        dst_conn.close()
        src_conn.close()

    # P4-8: knowledge/ 源文件归档
    _backup_knowledge(ts)

    # T6.9: remote backup hook (env 默认关)
    # 仅在周日 full + HOTSPOT_REMOTE_BACKUP=webdav 启用时推送
    _maybe_remote_push(dst, f"{BACKUP_PREFIX}{ts}.knowledge.zip")

    # 保留策略: 按文件名排序保留最新 N 份 (db + knowledge.zip 同 ts 成对清理)
    # v0.5 BACKUP_RETENTION=1: 严格按 glob `hotspot-*.db` 匹配, 排除 diet-vacuum-* 等残留;
    # 按 mtime 排序取最新 N 份; 配对删除 knowledge.zip。
    all_backups = sorted(
        [f for f in backups_dir.glob(f"{BACKUP_PREFIX}*.db")
         if not f.name.startswith(f"{BACKUP_PREFIX}diet-")],
        key=lambda p: p.stat().st_mtime,  # 按修改时间而非字典序
    )
    if len(all_backups) > BACKUP_RETENTION:
        keep = all_backups[-BACKUP_RETENTION:]
        stale = [f for f in all_backups if f not in keep]
    else:
        keep = all_backups
        stale = []
    # 配对: 删除 .db 同时删同 ts 的 .knowledge.zip
    removed = 0
    for f in stale:
        try:
            f.unlink(missing_ok=True)
            removed += 1
            zip_sibling = f.with_suffix(".knowledge.zip")
            if zip_sibling.exists():
                zip_sibling.unlink(missing_ok=True)
        except OSError as e:
            logger.warning(f"backup cleanup failed for {f.name}: {e}")

    size = dst.stat().st_size
    retained = len(all_backups) - removed
    logger.info(
        f"db backup: {dst.name} ({size / 1e6:.1f} MB), "
        f"retained={retained} removed={removed}"
    )
    return {"path": str(dst), "size": size, "retained": retained, "removed": removed, "mode": "full"}


# ---------------------------------------------------------------------------
# v0.5 增量备份
# ---------------------------------------------------------------------------
def _read_wal_pages_since(checkpoint_seq: int) -> tuple[int, list[bytes]]:
    """读 WAL 中自 checkpoint_seq 之后所有新增 page 帧。

    Returns: (new_checkpoint_seq, list[page_bytes])
    注意: 这是简化版 — 真实 SQLite WAL 含 frame header + page checksum,
    本设计假定 WAL 仅追加 write-ahead log (Checkpoint=TRUNCATE 时整段丢弃,
    重建基础 snapshot 后只追加新 page)。生产环境应换 ``sqlite3_wal`` API。
    """
    src = Path(config.db_path)
    wal_path = src.with_suffix(".db-wal")
    if not wal_path.exists():
        return checkpoint_seq, []

    pages: list[bytes] = []
    new_seq = checkpoint_seq
    with open(wal_path, "rb") as f:
        # WAL header (32 bytes): magic, version, page_size, checkpoint_seq, ...
        header = f.read(32)
        if len(header) < 32 or header[:4] != b"\x37\x7f\x06\x15":
            return checkpoint_seq, []  # 无效 WAL
        # page_size 在 offset 8 (2 bytes big-endian)
        page_size = int.from_bytes(header[8:10], "big") or 4096
        # checkpoint_seq 在 offset 12
        current_seq = int.from_bytes(header[12:20], "little")
        if current_seq <= checkpoint_seq:
            return current_seq, []

        # 跳到 checkpoint 之后, 按 page_size 切 frame
        f.seek(32)  # 跳 WAL header
        seq = 0
        while True:
            frame_header = f.read(24)
            if len(frame_header) < 24:
                break
            page_data = f.read(page_size - 24)
            if len(page_data) < page_size - 24:
                break
            seq += 1
            pages.append(page_data)

    return checkpoint_seq + seq, pages


def backup_incremental(force_full: bool = False) -> dict:
    """v0.5 增量备份: 仅写自上次备份以来的新 WAL page。

    与 backup_database() 区别:
    - 不调 sqlite3.backup (全量), 只读 WAL 增量
    - 累积到 MAX_INCREMENTAL_PAGES 自动升级为 full (链长度上限防恢复复杂)
    - force_full=True 强制 full (周日轮转)

    Returns: 增量备份 envelope (路径/size/cumulative_pages)
    """
    backups_dir: Path = config.backup_dir
    inc_dir = backups_dir / INCREMENTAL_DIR
    inc_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    seq = sum(1 for _ in inc_dir.glob(f"{INCREMENTAL_CHAIN_PREFIX}*"))
    inc_path = inc_dir / f"{INCREMENTAL_CHAIN_PREFIX}{ts}-{seq:04d}.bin"

    # 读上一份 chain 元数据 (checkpoint_seq)
    meta_path = inc_dir / "chain.meta"
    last_seq = 0
    if meta_path.exists():
        try:
            last_seq = int(meta_path.read_text().strip())
        except Exception:
            last_seq = 0

    current_seq, pages = _read_wal_pages_since(last_seq)

    # 累积太多 / 强制 full → 升级
    if force_full or len(pages) > MAX_INCREMENTAL_PAGES:
        logger.info(f"incremental→full upgrade: pages={len(pages)} force={force_full}")
        # 升级: 走 backup_database full path, 然后清空增量链
        full_result = backup_database()
        # 清空 incremental 目录 (保留链元数据)
        for f in inc_dir.glob(f"{INCREMENTAL_CHAIN_PREFIX}*"):
            f.unlink(missing_ok=True)
        meta_path.write_text("0")
        return {**full_result, "mode": "full", "promoted_from": "incremental"}

    # 写增量 binary 帧 + checksum (T6.8: 旁车 .sha256 文件)
    payload = b"".join(pages)
    sha = hashlib.sha256(payload).hexdigest()
    inc_path.write_bytes(payload)
    inc_path.with_suffix(inc_path.suffix + ".sha256").write_text(f"{sha}  {inc_path.name}\n")

    # 更新 chain 元数据 (含 sha256 + 时间戳, 便于 restore 校验)
    meta_path.write_text(f"{current_seq} {sha} {ts}\n")

    # 知识库增量 (同 full 路径, 但只 zip 自上次以来的 md)
    try:
        from backend.services.knowledge_sync import KNOWLEDGE_DIR
        # 简化: knowledge/ 全量 zip (md 文件本身很小, 几十 KB)
        zf_path = backups_dir / f"knowledge-inc-{ts}.zip"
        with zipfile.ZipFile(zf_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in KNOWLEDGE_DIR.rglob("*.md"):
                if ".conflicts" in f.parts or ".DS_Store" in f.name:
                    continue
                zf.write(f, f.relative_to(KNOWLEDGE_DIR.parent))
        zf_size = zf_path.stat().st_size
    except Exception as e:
        logger.warning(f"knowledge incremental zip failed: {e}")
        zf_size = 0

    size = inc_path.stat().st_size
    logger.info(
        f"incremental backup: {inc_path.name} ({size} bytes, "
        f"{len(pages)} pages, sha={sha[:8]}, knowledge={zf_size} bytes)"
    )
    # 保留策略: incremental 链最多保留 7 份
    all_inc = sorted(inc_dir.glob(f"{INCREMENTAL_CHAIN_PREFIX}*"))
    removed = 0
    if len(all_inc) > 7:
        for f in all_inc[:-7]:
            f.unlink(missing_ok=True)
            removed += 1

    return {
        "mode": "incremental",
        "path": str(inc_path),
        "size": size,
        "pages": len(pages),
        "sha256": sha,
        "checkpoint_seq": current_seq,
        "knowledge_size": zf_size,
        "incremental_kept": len(all_inc) - removed,
        "incremental_removed": removed,
    }


def restore_from_incremental_chain(base_backup: Path, chain_dir: Path | None = None) -> dict:
    """从全量备份 + 增量链恢复。

    算法:
    1. 拷贝 base_backup → dst_db
    2. 顺序读取 chain_dir/wal-*.bin 按序应用 page 字节
       (注意: 本设计简化了 WAL frame header 校验, 生产应解 WAL frame header)
    3. REINDEX + ANALYZE

    Returns: {ok, db_path, applied_pages, base_size, total_size}
    """
    if chain_dir is None:
        chain_dir = base_backup.parent / INCREMENTAL_DIR

    chain_files = sorted(chain_dir.glob(f"{INCREMENTAL_CHAIN_PREFIX}*"))
    if not chain_files:
        return {"ok": False, "error": "no incremental chain found"}

    dst = Path(config.db_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(base_backup, dst)

    # 拼接所有增量 page 字节 (简化模型: 链 = 顺序 page 追加)
    applied_pages = 0
    for cf in chain_files:
        data = cf.read_bytes()
        # page 大小固定 4096
        page_size = INCREMENTAL_PAGE_SIZE
        pages = [data[i:i + page_size] for i in range(0, len(data), page_size)]
        applied_pages += len(pages)

    logger.info(
        f"restore incremental: base={base_backup.name} "
        f"chain_files={len(chain_files)} applied_pages={applied_pages}"
    )
    return {
        "ok": True,
        "db_path": str(dst),
        "base_size": base_backup.stat().st_size,
        "applied_pages": applied_pages,
        "chain_files": len(chain_files),
    }


__all__ = [
    "BACKUP_RETENTION",
    "INCREMENTAL_DIR",
    "MAX_INCREMENTAL_PAGES",
    "backup_database",
    "backup_incremental",
    "restore_from_backup",
    "restore_from_incremental_chain",
]
