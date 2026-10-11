"""数据库自动备份 service — 每日快照 + 保留策略。

用 SQLite 的 **online backup API** (``Connection.backup``): 在 WAL 模式下
对运行中的服务安全 — 拷贝期间源库可继续读写, 得到一致性快照 (等价
``sqlite3 <db> ".backup <dst>"`` 的 Python 版)。

P4-8 (2026-08-16): 备份完整性 — 除 DB 快照外, 同时打包 ``knowledge/``
源文件 (知识库 .md 是本机真相源, 此前仅靠 git, 无独立备份/恢复流程)。
备份目录结构:
  backups/hotspot-{ts}.db              ← HOT SQLite 快照
  backups/hotspot-warm-{ts}.db         ← WARM SQLite 快照 (P0-C 新增)
  backups/hotspot-cold-{ts}.db         ← COLD SQLite 快照 (P0-C 新增)
  backups/hotspot-{ts}.knowledge.zip   ← knowledge/ 源文件归档
  backups/backup-manifest-{ts}.json    ← 三库 manifest (path/size/sha256)

保留策略: 默认每族保留最近 ``BACKUP_RETENTION`` (3) 份, 超龄自动删除。

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
import json
import os
import shutil
import sqlite3
import struct
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.config import config
from backend.logging_config import logger


def _secure_artifact(path: Path) -> None:
    """备份产物权限收紧 0600 — v0.8.6 P0-9 / 审计 F0-12b (R6)。

    备份 .db / knowledge zip / 增量 .bin 与线上库同含 llm_secrets 密文
    与全量正文, 落盘默认 0644 等于把库复制成全机可读。失败仅 warning
    (权限不阻断备份链)。
    """
    try:
        os.chmod(path, 0o600)
    except OSError as e:
        logger.warning(f"chmod 0600 failed for {path}: {e}")

# P0-C: 1 → 3 (单份保留 = 任何一次写坏/删错即丢全部备份); 每族 (hot/warm/cold)
# 独立计数, 7 天一次 full snapshot 轮转不变。
# DEV-0323 滚动保留模型: HOT 只留最新 1 份 full — 冗余消除由
# compact_backup_chain() 的 roll-forward 合成保证 (full + 最旧增量合成
# 新 full 后删旧 full, 恢复点不丢), warm/cold 侧库无增量机制仍各留 3 份。
BACKUP_RETENTION = 1              # HOT full 保留份数 (不变量: 1)
SIDE_DB_RETENTION = 3             # WARM/COLD 侧库各自保留份数
BACKUP_PREFIX = "hotspot-"
MANIFEST_PREFIX = "backup-manifest-"
MANIFEST_KEEP = 14                # manifest JSON 保留份数 (约两周)

# 增量备份参数
INCREMENTAL_PAGE_SIZE = 4096      # SQLite 默认 page size
INCREMENTAL_DIR = "incremental"   # backups/{INCREMENTAL_DIR}/ 存增量
MAX_INCREMENTAL_PAGES = 8192      # 32MB 上限 (足够容下一次完整日采集)
INCREMENTAL_CHAIN_PREFIX = "wal-" # wal-{ts}-{seq}.bin 命名
INCREMENTAL_KEEP = 3              # DEV-0323: 增量链保留档数 (超出 → roll-forward 合成)
KNOWLEDGE_INC_KEEP = 3            # knowledge-inc-*.zip 与增量链同档数
# 增量 .bin 格式 (P0-C v2, 自描述):
#   header: magic b"WIB1" (4B) + page_size (4B big-endian)
#   record: page_no (4B big-endian, 1-based) + page data (page_size 字节)
# 旧格式 (纯 page 拼接, 无页号) 无法定位写入 offset, 且历史产物全为 0 字节,
# 不做兼容读取。
INCREMENTAL_BIN_MAGIC = b"WIB1"


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
        _secure_artifact(dst)  # P0-9/F0-12b: 全量正文 zip 0600
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
        from urllib.parse import quote

        import requests

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


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_sha_sidecar(path: Path) -> str:
    """写旁车 .sha256 (格式 `sha  filename`, sha256sum 兼容), 返回 sha。"""
    sha = _sha256_file(path)
    sidecar = path.with_suffix(path.suffix + ".sha256")
    sidecar.write_text(f"{sha}  {path.name}\n")
    _secure_artifact(sidecar)  # P0-9/F0-12b
    return sha


def _snapshot_db(src: Path, dst: Path) -> int:
    """SQLite online backup API 一致性快照, 返回 dst 字节数。

    P0-C: 产物 0 字节 = 备份失败 (源损坏/未写页), 必须 raise 而非静默成功 —
    此前 job 每天 "成功" 但 warm 库 899MB 从未被备份。
    P2: 0 字节失败路径先清理残留目标文件再 raise, 避免空文件被后续
    保留策略/校验当作有效备份产物。
    """
    src_conn = sqlite3.connect(str(src))
    dst_conn = sqlite3.connect(str(dst))
    try:
        src_conn.backup(dst_conn)
        dst_conn.commit()
    finally:
        dst_conn.close()
        src_conn.close()
    size = dst.stat().st_size
    if size == 0:
        dst.unlink(missing_ok=True)
        logger.error(f"backup artifact is 0 bytes: {dst} (src={src})")
        raise RuntimeError(f"backup artifact is 0 bytes: {dst.name} (src={src})")
    _secure_artifact(dst)  # P0-9/F0-12b: 快照与线上库同密级
    return size


def backup_side_dbs(ts: str, extra_entries: list[dict] | None = None) -> list[dict]:
    """P0-C: WARM/COLD 库备份 — 此前 daily job 只覆盖主库, warm 库零策略备份。

    每库走 SQLite Connection.backup() + sha256 旁车 + 汇总 manifest JSON;
    源库不存在则跳过 (info); 产物 0 字节直接 raise (不静默成功)。
    保留策略: 每族 (warm/cold) 各留 BACKUP_RETENTION 份, manifest 留 MANIFEST_KEEP 份。
    """
    backups_dir: Path = config.backup_dir
    backups_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = list(extra_entries or [])
    for kind, src_path in (("warm", Path(config.warm_db_path)), ("cold", Path(config.cold_db_path))):
        if not src_path.exists():
            logger.info(f"side db backup skip: {kind} not present ({src_path})")
            continue
        dst = backups_dir / f"{BACKUP_PREFIX}{kind}-{ts}.db"
        size = _snapshot_db(src_path, dst)  # 0 字节时 raise
        sha = _write_sha_sidecar(dst)
        entries.append({"kind": kind, "path": str(dst), "size": size, "sha256": sha})
        logger.info(f"side db backup: {dst.name} ({size / 1e6:.1f} MB)")

    manifest_path = backups_dir / f"{MANIFEST_PREFIX}{ts}.json"
    manifest_path.write_text(
        json.dumps({"ts": ts, "dbs": entries}, ensure_ascii=False, indent=2)
    )
    _secure_artifact(manifest_path)  # P0-9/F0-12b

    # 每族独立保留策略 (hot 全量走 backup_database 自己的清理, 不在此处;
    # DEV-0323: 侧库档数拆独立常量 SIDE_DB_RETENTION)
    for kind in ("warm", "cold"):
        family = sorted(
            backups_dir.glob(f"{BACKUP_PREFIX}{kind}-*.db"),
            key=lambda p: p.stat().st_mtime,
        )
        for stale in family[:-SIDE_DB_RETENTION] if len(family) > SIDE_DB_RETENTION else []:
            try:
                stale.unlink(missing_ok=True)
                stale.with_suffix(stale.suffix + ".sha256").unlink(missing_ok=True)
            except OSError as e:
                logger.warning(f"side db backup cleanup failed for {stale.name}: {e}")
    manifests = sorted(
        backups_dir.glob(f"{MANIFEST_PREFIX}*.json"), key=lambda p: p.stat().st_mtime
    )
    for stale in manifests[:-MANIFEST_KEEP] if len(manifests) > MANIFEST_KEEP else []:
        stale.unlink(missing_ok=True)
    return entries


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
        _secure_artifact(dst)  # P0-9/F0-12b: 恢复后的线上库同密级
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
    # P0-C: 走 _snapshot_db — 0 字节产物 raise, 不再静默成功
    size = _snapshot_db(src, dst)
    hot_sha = _write_sha_sidecar(dst)

    # P4-8: knowledge/ 源文件归档
    _backup_knowledge(ts)

    # P0-C: WARM/COLD 同批备份 + 三库 manifest (0 字节 / 缺失行为见 backup_side_dbs)
    # full 的 checkpoint_seq 入 manifest — 供 checker 校验链是否至少不早于 full
    hot_entry = {
        "kind": "hot",
        "path": str(dst),
        "size": size,
        "sha256": hot_sha,
        "checkpoint_seq": _read_wal_header_seq(src.with_suffix(".db-wal")),
    }
    side_entries = backup_side_dbs(ts, extra_entries=[hot_entry])

    # T6.9: remote backup hook (env 默认关)
    # 仅在周日 full + HOTSPOT_REMOTE_BACKUP=webdav 启用时推送
    _maybe_remote_push(dst, f"{BACKUP_PREFIX}{ts}.knowledge.zip")

    # 保留策略: 每族保留最新 BACKUP_RETENTION 份。
    # P0-C: glob 收紧为 `hotspot-[0-9]*.db` (ts 以数字开头) — 旧的 `hotspot-*.db`
    # 会把新增的 hotspot-warm-*/hotspot-cold-* 混进 hot 族误删。
    all_backups = sorted(
        backups_dir.glob(f"{BACKUP_PREFIX}[0-9]*.db"),
        key=lambda p: p.stat().st_mtime,  # 按修改时间而非字典序
    )
    if len(all_backups) > BACKUP_RETENTION:
        keep = all_backups[-BACKUP_RETENTION:]
        stale = [f for f in all_backups if f not in keep]
    else:
        keep = all_backups
        stale = []
    # 配对: 删除 .db 同时删同 ts 的 .knowledge.zip 与 .sha256
    removed = 0
    for f in stale:
        try:
            f.unlink(missing_ok=True)
            removed += 1
            zip_sibling = f.with_suffix(".knowledge.zip")
            if zip_sibling.exists():
                zip_sibling.unlink(missing_ok=True)
            f.with_suffix(f.suffix + ".sha256").unlink(missing_ok=True)
        except OSError as e:
            logger.warning(f"backup cleanup failed for {f.name}: {e}")

    retained = len(all_backups) - removed
    logger.info(
        f"db backup: {dst.name} ({size / 1e6:.1f} MB), "
        f"retained={retained} removed={removed}, side_dbs={len(side_entries)}"
    )
    return {
        "path": str(dst),
        "size": size,
        "retained": retained,
        "removed": removed,
        "mode": "full",
        # side_entries 已含 hot (extra_entries 原样带回)
        "dbs": list(side_entries),
    }


# ---------------------------------------------------------------------------
# v0.5 增量备份
# ---------------------------------------------------------------------------
def _wal_checksum(data: bytes, s0: int, s1: int, big_endian: bool) -> tuple[int, int]:
    """SQLite WAL 累积 checksum (wal.c walChecksumBytes 的 Python 等价实现)。

    - data 长度必须是 8 的倍数 (每次吞两个 u32 word);
    - word 字序由 WAL magic 决定 (0x377f0682 = little-endian / 0x377f0615 =
      big-endian), 与宿主机字节序无关;
    - 存储 (header 24-31 / frame header 16-23) 恒为 big-endian u32;
    - 算法: s0 += x[i] + s1; s1 += x[i+1] + s0 (mod 2^32), 累积值跨帧传递。
    已对真实 SQLite 3.53 写出的 WAL 帧序列验证 (生产库副本实测 6/6 帧全验)。
    """
    n = len(data) // 4
    words = struct.unpack((">" if big_endian else "<") + str(n) + "I", data)
    for i in range(0, n, 2):
        s0 = (s0 + words[i] + s1) & 0xFFFFFFFF
        s1 = (s1 + words[i + 1] + s0) & 0xFFFFFFFF
    return s0, s1


def _read_wal_header_seq(wal_path: Path) -> int:
    """读 WAL header 的 checkpoint_seq (offset 12, 4B big-endian); 无/坏 WAL 返 0。"""
    try:
        header = wal_path.read_bytes()[:32]
        if len(header) < 32:
            return 0
        return int.from_bytes(header[12:16], "big")
    except OSError:
        return 0


def _read_wal_pages_since(
    checkpoint_seq: int,
) -> tuple[int, list[tuple[int, bytes]], int]:
    """读 WAL 中所有有效 (valid) 的已 commit page 帧。

    P0-C 修复:
    - WAL magic 只取前 3 字节 (``37 7f 06``); 第 4 字节是 checksum 字节序标志
      (0x82 = little-endian words / 0x15 = big-endian words), 本机实测为 0x82 —
      旧代码硬编码 ``\\x37\\x7f\\x06\\x15`` 导致判断恒假, 增量备份永远产出空链。
    - checkpoint_seq 按 WAL header offset 12 的 4 字节 big-endian 读 (旧代码
      误按 8 字节小端); page_size 同理是 offset 8 的 4 字节大端。
    - 帧 = 24B frame header + page_size 字节页数据 (旧代码按 4096-24 切帧,
      第 2 帧起错位)。
    - **逐帧累积 checksum 校验** (P0-C 残余修复): 先验 WAL header 校验和
      (seed 0,0, 覆盖 header 前 24 字节), 之后每帧累积 frame header 前 8 字节
      + 页数据, 与帧头 16-23 存储值 (big-endian) 比对; 读到**第一个无效帧即停**
      (标准 SQLite 读取器行为)。无此校验时, 热读 live WAL 会把"被新事务覆写中
      的旧帧"(同代 salt 相同, 只有 checksum 能识别) 或半写入撕裂帧当有效页写进
      .bin, 应用后 b-tree 结构破坏 (integrity: malformed)。salt 校验保留为快速预筛。
    - 只保留最后一个 commit 帧及之前的内容 (未 commit 的事务不进备份)。
    - 不按 checkpoint_seq 闸门跳过: 全新 WAL 的 seq 从 0 开始, 与 last_seq=0
      相等会被误判 "无新增" 而产出空链 (P0-C 实测); 且未 checkpoint 只追加帧时
      seq 根本不变。WAL 全量重放幂等 (每页的最后一帧 = 最新已 commit 版本),
      重复页无害, checkpoint_seq 仅作元数据记账。

    Returns: (new_checkpoint_seq, [(page_no, page_bytes)], page_size)
    """
    src = Path(config.db_path)
    wal_path = src.with_suffix(".db-wal")
    if not wal_path.exists():
        return checkpoint_seq, [], INCREMENTAL_PAGE_SIZE

    frames: list[tuple[int, bytes, int]] = []  # (pgno, page, commit_size)
    stop_reason = "eof"
    with open(wal_path, "rb") as f:
        # WAL header (32 bytes): magic(4) version(4) page_size(4) checkpoint_seq(4)
        #                        salt1(4) salt2(4) checksum1(4) checksum2(4)
        header = f.read(32)
        if len(header) < 32:
            return checkpoint_seq, [], INCREMENTAL_PAGE_SIZE
        if header[:3] != b"\x37\x7f\x06" or header[3] not in (0x15, 0x82):
            logger.warning(f"invalid WAL magic {header[:4].hex()}: {wal_path}")
            return checkpoint_seq, [], INCREMENTAL_PAGE_SIZE
        big_endian_ck = header[3] == 0x15
        version = int.from_bytes(header[4:8], "big")
        if version != 3007000:
            logger.warning(f"unsupported WAL format version {version}: {wal_path}")
            return checkpoint_seq, [], INCREMENTAL_PAGE_SIZE
        page_size = int.from_bytes(header[8:12], "big")
        if page_size < 512 or page_size > 65536 or page_size & (page_size - 1):
            logger.warning(f"invalid WAL page_size {page_size}: {wal_path}")
            return checkpoint_seq, [], INCREMENTAL_PAGE_SIZE
        current_seq = int.from_bytes(header[12:16], "big")
        salt = header[16:24]

        # header 自身 checksum 不过 → 整个 WAL 视为空 (标准读取器行为)
        s0, s1 = _wal_checksum(header[:24], 0, 0, big_endian_ck)
        if s0 != int.from_bytes(header[24:28], "big") or s1 != int.from_bytes(
            header[28:32], "big"
        ):
            logger.warning(f"WAL header checksum mismatch, treat as empty: {wal_path}")
            return checkpoint_seq, [], page_size

        f.seek(32)
        while True:
            frame_header = f.read(24)
            if len(frame_header) < 24:
                break
            pgno = int.from_bytes(frame_header[0:4], "big")
            commit_size = int.from_bytes(frame_header[4:8], "big")
            if frame_header[8:16] != salt:
                stop_reason = f"salt mismatch at frame {len(frames)}"
                break
            page = f.read(page_size)
            if len(page) < page_size:
                stop_reason = f"truncated page at frame {len(frames)}"
                break
            c0, c1 = _wal_checksum(frame_header[:8] + page, s0, s1, big_endian_ck)
            if (
                pgno == 0
                or c0 != int.from_bytes(frame_header[16:20], "big")
                or c1 != int.from_bytes(frame_header[20:24], "big")
            ):
                # 首个无效帧 = WAL 有效结尾 (覆写中 / 撕裂 / 回滚残留帧)
                stop_reason = f"checksum invalid at frame {len(frames)}"
                break
            s0, s1 = c0, c1
            frames.append((pgno, page, commit_size))

    if stop_reason != "eof":
        logger.info(f"wal scan: {len(frames)} valid frames, stopped early: {stop_reason}")

    # 只保留到最后一个 commit 帧 (其后的帧属于未 commit 事务)
    last_commit = -1
    for i, (_, _, commit_size) in enumerate(frames):
        if commit_size:
            last_commit = i
    pages = [(pgno, page) for pgno, page, _ in frames[: last_commit + 1]]
    return current_seq, pages, page_size


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
    # P0-C: 只数 .bin (旧 glob `wal-*` 会把 .sha256 旁车也计入, 序号虚高)
    seq = sum(1 for _ in inc_dir.glob(f"{INCREMENTAL_CHAIN_PREFIX}*.bin"))
    inc_path = inc_dir / f"{INCREMENTAL_CHAIN_PREFIX}{ts}-{seq:04d}.bin"

    # 读上一份 chain 元数据 (checkpoint_seq)
    # P0-C: meta 实际格式为 `seq sha ts [pages]`, 旧代码 int(整行) 恒抛异常
    # 被吞掉, last_seq 永远回退为 0
    meta_path = inc_dir / "chain.meta"
    last_seq = 0
    if meta_path.exists():
        try:
            last_seq = int(meta_path.read_text().split()[0])
        except (ValueError, IndexError):
            last_seq = 0

    current_seq, pages, page_size = _read_wal_pages_since(last_seq)

    # 累积太多 / 强制 full → 升级
    if force_full or len(pages) > MAX_INCREMENTAL_PAGES:
        logger.info(f"incremental→full upgrade: pages={len(pages)} force={force_full}")
        # 升级: 走 backup_database full path (含 WARM/COLD), 然后清空增量链
        full_result = backup_database()
        # 清空 incremental 目录 (保留链元数据)
        for f in inc_dir.glob(f"{INCREMENTAL_CHAIN_PREFIX}*.bin"):
            f.unlink(missing_ok=True)
            f.with_suffix(f.suffix + ".sha256").unlink(missing_ok=True)
        meta_path.write_text("0")
        return {**full_result, "mode": "full", "promoted_from": "incremental"}

    # P0-C: WARM/COLD 库每日备份 (HOT 走增量链, warm/cold 无增量机制只能全量)
    side_entries = backup_side_dbs(ts)

    # 写增量 binary: header (magic + page_size) + records (pgno + page data)
    # T6.8: 旁车 .sha256 文件
    payload = INCREMENTAL_BIN_MAGIC + page_size.to_bytes(4, "big")
    payload += b"".join(
        pgno.to_bytes(4, "big") + page for pgno, page in pages
    )
    sha = hashlib.sha256(payload).hexdigest()
    inc_path.write_bytes(payload)
    _secure_artifact(inc_path)  # P0-9/F0-12b
    inc_path.with_suffix(inc_path.suffix + ".sha256").write_text(f"{sha}  {inc_path.name}\n")
    _secure_artifact(inc_path.with_suffix(inc_path.suffix + ".sha256"))  # P0-9/F0-12b

    if not pages:
        # P0-C: 不再静默 "成功" — WAL 存在但没读到帧时告警留痕
        logger.warning(
            f"incremental backup has 0 pages (wal_seq={current_seq}, last_seq={last_seq})"
        )

    # 更新 chain 元数据 (seq + sha256 + 时间戳 + 页数, 便于 restore/checker 校验)
    meta_path.write_text(f"{current_seq} {sha} {ts} {len(pages)}\n")

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
        _secure_artifact(zf_path)  # P0-9/F0-12b
        zf_size = zf_path.stat().st_size
    except Exception as e:
        logger.warning(f"knowledge incremental zip failed: {e}")
        zf_size = 0

    # DEV-0323 滚动保留不变量: 1 full + INCREMENTAL_KEEP 档。超出不再直接
    # 删最旧档 (旧 >7 截断会丢覆盖范围且留 3 份 full 冗余), 改走
    # roll-forward 合成 + 旧 full/残档/超额 knowledge-inc zip 清理。
    size = inc_path.stat().st_size
    logger.info(
        f"incremental backup: {inc_path.name} ({size} bytes, "
        f"{len(pages)} pages, sha={sha[:8]}, knowledge={zf_size} bytes, "
        f"side_dbs={len(side_entries)})"
    )
    before = len(list(inc_dir.glob(f"{INCREMENTAL_CHAIN_PREFIX}*.bin")))
    compaction = compact_backup_chain(INCREMENTAL_KEEP)
    if not compaction["ok"]:
        # 合成失败 = 链/盘有异常, 但本次增量备份已成功 → 不 raise, 留痕
        # (daily job 层据此告警; 下次 daily 会重试同一不变量)
        logger.error(f"backup compact failed after incremental: {compaction['error']}")
    removed = before - compaction["chain_active"]

    return {
        "mode": "incremental",
        "path": str(inc_path),
        "size": size,
        "pages": len(pages),
        "sha256": sha,
        "checkpoint_seq": current_seq,
        "knowledge_size": zf_size,
        "incremental_kept": compaction["chain_active"],
        "incremental_removed": max(0, removed),
        "compaction": compaction,
        "side_dbs": side_entries,
    }


def compact_backup_chain(keep_incrementals: int = INCREMENTAL_KEEP) -> dict:
    """DEV-0323 滚动保留不变量执行器: **1 个最新 full + ≤keep 档增量**。

    超出时对最旧档做 roll-forward 合成 (用户模型「每次清理前用全量+最旧
    增量合成第二个全量, 然后去掉最旧的全量」):

    1. 链文件数 > keep → absorb = 最旧的超额档; 把 full 副本上逐页重放
       absorb (apply_incremental_chain, 预校验 sha/magic + integrity_check,
       失败零接触) 得新 full — 覆盖状态前进到 absorb 末档时刻
    2. 新 full mtime 钉在 absorb 末档的 mtime — 保住 check_backup_chain
       「只认 mtime ≥ full 的 bin」的链过滤语义 (剩余档恰好晚于新 full)
    3. 删 absorb 链档 (已并入新 full, 留着才是冗余) + 旧 full 及其
       zip/sha/manifest 配套, 剩余链 = 最新 keep 档
    4. 页重放是 last-write-wins, absorb 被跳过不破坏恢复正确性;
       合成失败 (坏链) 一切原样保留并返回 ok=False (fail-loud,
       绝不在未验证的新 full 存在时删旧 base)

    顺带清理 (同"不冗余"不变量):
    - 超出的旧 full (mtime 排序保留最新 BACKUP_RETENTION 份; 无链依赖 —
      full 轮转本就连链一起清空, 旧 full 的全部支撑链已失效)
    - mtime 早于保留 full 的残档 (stale chain, checker 本来就排除)
    - knowledge-inc-*.zip 超出 KNOWLEDGE_INC_KEEP 份

    Returns 摘要 envelope (compacted/ok/absorbed/new_full/removed_*/chain_active)。
    """
    backups_dir: Path = config.backup_dir
    inc_dir = backups_dir / INCREMENTAL_DIR
    result: dict = {
        "ok": True, "compacted": False, "error": None,
        "new_full": None, "absorbed_bins": [],
        "removed_fulls": [], "removed_stale_bins": [],
        "removed_knowledge_inc": 0, "chain_active": 0,
    }
    fulls = sorted(
        backups_dir.glob(f"{BACKUP_PREFIX}[0-9]*.db"),
        key=lambda p: p.stat().st_mtime,
    )
    if not fulls:
        result["ok"] = False
        result["error"] = "no HOT full backup found (nothing to compact against)"
        logger.error(f"backup compact: {result['error']}")
        return result

    keep_full = fulls[-1]
    all_bins = sorted(
        inc_dir.glob(f"{INCREMENTAL_CHAIN_PREFIX}*.bin"),
        key=lambda p: p.stat().st_mtime,
    ) if inc_dir.exists() else []
    full_mtime = keep_full.stat().st_mtime
    # 活跃链 = mtime >= 保留 full (与 check_backup_chain 过滤语义一致);
    # 早于 full 的残档对最新恢复点无效 (checker 排除 / restore 重放会回退页)
    active = [b for b in all_bins if b.stat().st_mtime >= full_mtime]

    # ── roll-forward 合成 (仅超额时) ──────────────────────────────
    if len(active) > keep_incrementals:
        absorb = active[: len(active) - keep_incrementals]
        tmp = keep_full.with_name(f".compact-{int(time.time() * 1000)}-{os.getpid()}")
        shutil.copy2(keep_full, tmp)
        applied = apply_incremental_chain(tmp, absorb)
        if not applied.get("ok"):
            tmp.unlink(missing_ok=True)
            result["ok"] = False
            result["error"] = f"apply chain failed: {applied.get('error', 'unknown')}"
            logger.error(f"backup compact FAILED, nothing deleted: {result['error']}")
            return result
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        new_full = backups_dir / f"{BACKUP_PREFIX}{ts}.db"
        # ts 秒粒度: 合成与 backup_database/上次合成同秒时文件名会撞上
        # 正被 os.replace 覆写/读取的 base 或既有 full (CI 测试实测抓出:
        # replace 同名覆写 base → _drop_full 删同名 → full 归零) → 顺秒避让
        while new_full.exists() or (
            backups_dir / f"{MANIFEST_PREFIX}{ts}.json"
        ).exists():
            ts = (datetime.strptime(ts, "%Y%m%d_%H%M%S")
                  + timedelta(seconds=1)).strftime("%Y%m%d_%H%M%S")
            new_full = backups_dir / f"{BACKUP_PREFIX}{ts}.db"
        os.replace(tmp, new_full)
        # mtime 钉到 absorb 末档 → 剩余 active 档的 mtime 必然 >= 新 full
        # (checker/verify 的链过滤与"最新 full"排序语义都不破)
        last_absorbed_mtime = absorb[-1].stat().st_mtime
        os.utime(new_full, (last_absorbed_mtime, last_absorbed_mtime))
        sha = _write_sha_sidecar(new_full)
        # 配对 knowledge zip: 最新 knowledge-inc (每日全量 md) 复制为新 full 伴生
        kinc = sorted(
            backups_dir.glob("knowledge-inc-*.zip"),
            key=lambda p: p.stat().st_mtime,
        )
        paired = keep_full.with_suffix(".knowledge.zip")  # 兜底: 旧 full 伴生 zip
        src_zip = kinc[-1] if kinc else (paired if paired.exists() else None)
        if src_zip is not None:
            shutil.copy2(src_zip, new_full.with_suffix(".knowledge.zip"))
        # manifest (checkpoint_seq=0: 合成 full 的覆盖 seq 无逐档记录可考,
        # 写 0 让 checker 的 seq 信息级对账如实跳过, 不编造数字)
        (backups_dir / f"{MANIFEST_PREFIX}{ts}.json").write_text(json.dumps(
            {"ts": ts, "dbs": [{
                "kind": "hot", "path": str(new_full),
                "size": new_full.stat().st_size, "sha256": sha,
                "checkpoint_seq": 0,
                "compact_of": {"base": keep_full.name,
                               "absorbed": [b.name for b in absorb]},
            }]},
            ensure_ascii=False, indent=2))
        _secure_artifact(new_full)
        for b in absorb:
            b.unlink(missing_ok=True)
            b.with_suffix(b.suffix + ".sha256").unlink(missing_ok=True)
        active = active[len(absorb):]
        # 旧 full (合成基) 被新 full 取代 → 删, 连带 zip/sha/manifest 配套
        _drop_full(keep_full, result["removed_fulls"])
        keep_full = new_full
        full_mtime = last_absorbed_mtime
        result["compacted"] = True
        result["new_full"] = new_full.name
        result["absorbed_bins"] = [b.name for b in absorb]

    # ── 超出保留的旧 full 清理 (不变量: 1 份) ─────────────────────
    fulls = sorted(
        backups_dir.glob(f"{BACKUP_PREFIX}[0-9]*.db"),
        key=lambda p: p.stat().st_mtime,
    )
    for old in fulls[:-BACKUP_RETENTION] if len(fulls) > BACKUP_RETENTION else []:
        _drop_full(old, result["removed_fulls"])

    # ── 残档/知识 zip 清理 ────────────────────────────────────────
    all_bins = sorted(
        inc_dir.glob(f"{INCREMENTAL_CHAIN_PREFIX}*.bin"),
        key=lambda p: p.stat().st_mtime,
    ) if inc_dir.exists() else []
    survivors = 0  # 残档在同一循环里判存 (删后不可再 stat 引用旧列表)
    for b in all_bins:
        if b.stat().st_mtime < full_mtime:
            b.unlink(missing_ok=True)
            b.with_suffix(b.suffix + ".sha256").unlink(missing_ok=True)
            result["removed_stale_bins"].append(b.name)
        else:
            survivors += 1
    kincs = sorted(
        backups_dir.glob("knowledge-inc-*.zip"),
        key=lambda p: p.stat().st_mtime,
    )
    for z in kincs[:-KNOWLEDGE_INC_KEEP] if len(kincs) > KNOWLEDGE_INC_KEEP else []:
        z.unlink(missing_ok=True)
        result["removed_knowledge_inc"] += 1

    # 孤儿 paired zip: hotspot-{ts}.knowledge.zip 但对应 full 主体已不存在
    # (旧轮转清理先于配对删除逻辑 / 手删主体 都会留下孤儿)
    removed_orphans = 0
    for kz in backups_dir.glob(f"{BACKUP_PREFIX}*.knowledge.zip"):
        ts = kz.name.removeprefix(BACKUP_PREFIX).removesuffix(".knowledge.zip")
        if not (backups_dir / f"{BACKUP_PREFIX}{ts}.db").exists():
            kz.unlink(missing_ok=True)
            removed_orphans += 1
    result["removed_knowledge_inc"] += removed_orphans

    result["chain_active"] = survivors
    logger.info(
        f"backup compact: compacted={result['compacted']} "
        f"absorbed={len(result['absorbed_bins'])} "
        f"removed_fulls={len(result['removed_fulls'])} "
        f"stale_bins={len(result['removed_stale_bins'])} "
        f"knowledge_inc_removed={result['removed_knowledge_inc']} "
        f"chain_active={result['chain_active']}"
    )
    return result


def _drop_full(full: Path, removed: list[str]) -> None:
    """删除 full 及其配套 (.knowledge.zip / .sha256 / manifest)。"""
    full.unlink(missing_ok=True)
    full.with_suffix(".knowledge.zip").unlink(missing_ok=True)
    full.with_suffix(full.suffix + ".sha256").unlink(missing_ok=True)
    ts = full.stem.removeprefix(f"{BACKUP_PREFIX}")
    (full.parent / f"{MANIFEST_PREFIX}{ts}.json").unlink(missing_ok=True)
    removed.append(full.name)


def backup_inventory() -> dict:
    """DEV-0323: 备份现状盘点 (备份卡状态展示的后端权威形状, 纯读)。"""
    backups_dir: Path = config.backup_dir
    inc_dir = backups_dir / INCREMENTAL_DIR
    now = datetime.now(timezone.utc)

    def _age(path: Path) -> float:
        mtime_utc = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        return round((now - mtime_utc).total_seconds() / 3600, 1)

    fulls = [
        {"name": p.name, "size_mb": round(p.stat().st_size / 1e6, 1),
         "age_hours": _age(p)}
        for p in sorted(backups_dir.glob(f"{BACKUP_PREFIX}[0-9]*.db"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    ]
    chain_files: list[dict] = []
    if inc_dir.exists():
        for p in sorted(inc_dir.glob(f"{INCREMENTAL_CHAIN_PREFIX}*.bin"),
                        key=lambda p: p.stat().st_mtime, reverse=True):
            size = p.stat().st_size
            pages = 0
            try:
                with open(p, "rb") as f:
                    head = f.read(8)
                if head[:4] == INCREMENTAL_BIN_MAGIC and len(head) == 8:
                    ps = int.from_bytes(head[4:8], "big")
                    if ps:
                        pages = (size - 8) // (4 + ps)
            except OSError:
                pass
            chain_files.append({"name": p.name, "size_kb": round(size / 1024, 1),
                                "pages": pages, "age_hours": _age(p)})
    k_zips = list(backups_dir.glob(f"{BACKUP_PREFIX}*.knowledge.zip"))
    k_incs = list(backups_dir.glob("knowledge-inc-*.zip"))
    total = sum(p.stat().st_size for p in backups_dir.rglob("*") if p.is_file())
    marker = None
    markers = sorted(backups_dir.glob("INTEGRITY_OK.*"),
                     key=lambda p: p.stat().st_mtime)
    if markers:
        marker = {"name": markers[-1].name, "age_hours": _age(markers[-1])}
    return {
        "checked_at": now.isoformat(),
        "policy": {"full_keep": BACKUP_RETENTION,
                   "incremental_keep": INCREMENTAL_KEEP,
                   "side_db_keep": SIDE_DB_RETENTION,
                   "invariant": "1 full + ≤3 增量档; 超出自动 roll-forward 合成"},
        "fulls": fulls,
        "chain": {"count": len(chain_files), "files": chain_files},
        "side_dbs": {
            "warm": len(list(backups_dir.glob(f"{BACKUP_PREFIX}warm-*.db"))),
            "cold": len(list(backups_dir.glob(f"{BACKUP_PREFIX}cold-*.db"))),
        },
        "knowledge": {"full_zip_count": len(k_zips), "inc_zip_count": len(k_incs)},
        "last_integrity_marker": marker,
        "totals": {"bytes": total, "mb": round(total / 1e6, 1)},
    }


def parse_incremental_bin(data: bytes) -> tuple[int, list[tuple[int, bytes]]]:
    """解析增量 .bin (P0-C v2 自描述格式), 返回 (page_size, [(pgno, page)])。

    校验: magic / page_size 合法 (512..65536 且为 2 的幂) / 记录长度整除。
    不合法直接 raise ValueError (宁可恢复失败, 不可写坏目标库)。
    """
    if len(data) < 8:
        raise ValueError(f"incremental file too small: {len(data)} bytes")
    if data[:4] != INCREMENTAL_BIN_MAGIC:
        raise ValueError(f"bad incremental magic: {data[:4].hex()}")
    page_size = int.from_bytes(data[4:8], "big")
    if page_size < 512 or page_size > 65536 or page_size & (page_size - 1):
        raise ValueError(f"invalid page_size in incremental file: {page_size}")
    body = data[8:]
    if len(body) % (4 + page_size):
        raise ValueError(
            f"truncated incremental file: body={len(body)} not multiple of {4 + page_size}"
        )
    pages: list[tuple[int, bytes]] = []
    off = 0
    while off < len(body):
        pgno = int.from_bytes(body[off:off + 4], "big")
        page = body[off + 4:off + 4 + page_size]
        if pgno == 0:
            raise ValueError("invalid page number 0 in incremental file")
        pages.append((pgno, page))
        off += 4 + page_size
    return page_size, pages


def apply_incremental_chain(target_db: Path, chain_files: list[Path]) -> dict:
    """把增量链原子写入目标 db 文件 (P0-C: 旧实现零写操作假报成功)。

    P1 恢复原子性: 先整体预校验 (magic/长度/sha256 旁车), 然后把目标复制到
    同目录 ``.restore-tmp-<ts>`` 临时文件, 在临时文件上逐页写入并跑
    PRAGMA integrity_check; 全部通过后才清掉目标残留 -wal/-shm 并
    ``os.replace`` 原子替换。任何一步失败: 删临时文件, 目标库零接触,
    返回 ok=False — 不会把目标库 (含 live config.db_path 恢复路径) 改写
    成损坏状态。checker 对 scratch 副本的调用同样走此逻辑, 无需特判。
    """
    # pass 1: 全链预校验 (任一文件坏 → 不写任何字节)
    parsed: list[tuple[int, list[tuple[int, bytes]]]] = []
    for cf in chain_files:
        data = cf.read_bytes()
        sha_file = cf.with_suffix(cf.suffix + ".sha256")
        if sha_file.exists():
            expected = sha_file.read_text().split()[0]
            actual = hashlib.sha256(data).hexdigest()
            if expected != actual:
                return {
                    "ok": False,
                    "error": f"sha256 mismatch for {cf.name}: "
                             f"expected={expected[:8]} actual={actual[:8]}",
                }
        try:
            parsed.append(parse_incremental_bin(data))
        except ValueError as e:
            return {"ok": False, "error": f"{cf.name}: {e}"}

    # pass 2: 在临时副本上逐页写入 (目标库零接触)
    applied_pages = 0
    tmp = target_db.with_name(f".restore-tmp-{int(time.time() * 1000)}-{os.getpid()}")
    integrity = "unknown"
    integrity_warn: str | None = None
    try:
        shutil.copy2(target_db, tmp)
        with open(tmp, "r+b") as f:
            for page_size, pages in parsed:
                for pgno, page in pages:
                    f.seek((pgno - 1) * page_size)
                    f.write(page)
                    applied_pages += 1
            f.flush()
            # 不做 truncate: 逻辑页数由 page 1 header 的 size-in-pages 字段决定,
            # 链外残尾 (仅当库自 base 后收缩过才存在) 会被 SQLite 忽略;
            # 盲 truncate 到最后写入位置会砍掉未在链中的尾页。

        conn = sqlite3.connect(str(tmp))
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
            integrity = row[0] if row else "unknown"
        except sqlite3.Error as e:
            # DatabaseError ("database disk image is malformed") 与 OperationalError
            # 都要接住 — 增量页破坏 b-tree 时必须返回 ok=False, 不能 traceback
            if "vtable constructor failed" in str(e):
                # 已知: standalone 环境缺 FTS5 module, 库文件本身可能完好
                integrity = "warn"
                integrity_warn = str(e)
            else:
                return {"ok": False, "applied_pages": applied_pages,
                        "integrity_check": "error", "error": str(e)}
        finally:
            conn.close()

        if integrity not in ("ok", "warn"):
            return {"ok": False, "db_path": str(target_db),
                    "applied_pages": applied_pages, "integrity_check": integrity,
                    "chain_files": len(chain_files),
                    "error": f"integrity_check failed: {integrity}"}

        # 全部通过: 清掉目标残留 sidecar (旧 -wal 里是 live 库的帧,
        # 混入被改写的 db 会直接判 corrupt) 后原子替换
        for suffix in ("-wal", "-shm"):
            stale = target_db.with_name(target_db.name + suffix)
            if stale.exists():
                logger.warning(f"restore: removing stale sidecar {stale.name}")
                stale.unlink(missing_ok=True)
        os.replace(tmp, target_db)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        return {"ok": False, "applied_pages": applied_pages,
                "error": f"apply failed: {e}"}
    finally:
        tmp.unlink(missing_ok=True)  # 成功路径已被 replace, 失败路径兜底清理

    result: dict = {
        "ok": True,
        "db_path": str(target_db),
        "applied_pages": applied_pages,
        "integrity_check": integrity,
        "chain_files": len(chain_files),
    }
    if integrity_warn:
        result["integrity_warn"] = integrity_warn
    return result


def restore_from_incremental_chain(base_backup: Path, chain_dir: Path | None = None) -> dict:
    """从全量备份 + 增量链恢复 (P0-C: 真实页写入 + integrity 校验)。

    算法:
    1. 拷贝 base_backup → 同目录 ``.restore-tmp-<ts>`` staging 文件
       (目标库零接触, 失败路径不留半成品)
    2. apply_incremental_chain: 预校验 (magic/sha256/长度) → 临时副本上
       按 (pgno-1)*page_size seek 写入每页 → PRAGMA integrity_check →
       通过后 os.replace 回 staging
    3. staging 替换目标库前清掉残留 -wal/-shm (旧 -wal 里是 live 库的帧,
       混入被改写的 db 会直接判 corrupt)
    4. 失败 (任一链文件非法 / integrity != ok) 返回 ok=False, 删 staging,
       目标库零接触, 不假报成功

    Returns: {ok, db_path, applied_pages, integrity_check, base_size, chain_files}
    """
    if not base_backup.exists():
        return {"ok": False, "error": f"base backup not found: {base_backup}"}
    if chain_dir is None:
        chain_dir = base_backup.parent / INCREMENTAL_DIR

    # 只取 .bin (旧 glob `wal-*` 会把 .sha256 旁车当链文件读)
    chain_files = sorted(chain_dir.glob(f"{INCREMENTAL_CHAIN_PREFIX}*.bin"))
    if not chain_files:
        return {"ok": False, "error": "no incremental chain found"}

    dst = Path(config.db_path)
    dst.parent.mkdir(parents=True, exist_ok=True)

    # 恢复原子性: base 先落 staging, 链全部应用且 integrity 通过后才替换目标
    # (前缀与 apply 的 .restore-tmp- 区分, 避免同毫秒命名碰撞)
    staging = dst.with_name(f".restore-base-{int(time.time() * 1000)}-{os.getpid()}")
    try:
        shutil.copy2(base_backup, staging)
    except OSError as e:
        staging.unlink(missing_ok=True)
        return {"ok": False, "error": f"copy base backup failed: {e}"}

    result = apply_incremental_chain(staging, chain_files)
    if result.get("ok"):
        try:
            os.replace(staging, dst)
        except OSError as e:
            staging.unlink(missing_ok=True)
            return {"ok": False, "error": f"atomic replace failed: {e}",
                    "base_size": base_backup.stat().st_size}
    else:
        staging.unlink(missing_ok=True)

    result["base_size"] = base_backup.stat().st_size
    if result.get("ok"):
        logger.info(
            f"restore incremental: base={base_backup.name} "
            f"chain_files={result['chain_files']} "
            f"applied_pages={result['applied_pages']} integrity={result['integrity_check']}"
        )
    else:
        logger.error(f"restore incremental failed: {result.get('error')}")
    return result


__all__ = [
    "BACKUP_RETENTION",
    "INCREMENTAL_BIN_MAGIC",
    "INCREMENTAL_DIR",
    "INCREMENTAL_KEEP",
    "MAX_INCREMENTAL_PAGES",
    "SIDE_DB_RETENTION",
    "apply_incremental_chain",
    "backup_database",
    "backup_incremental",
    "backup_inventory",
    "backup_side_dbs",
    "compact_backup_chain",
    "parse_incremental_bin",
    "restore_from_backup",
    "restore_from_incremental_chain",
]
