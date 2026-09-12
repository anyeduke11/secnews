"""P0-C 备份链修复测试 (FIRST_PRINCIPLES_ANALYSIS_2026-09-11 §0.1)。

覆盖:
- WAL 头两种 checksum 字节序 (0x15 / 0x82) 都被接受; 非法 magic 拒绝
- 增量 .bin 产物非空且为自描述 v2 格式 (WIB1 header + pgno 记录)
- restore_from_incremental_chain 真实页写入 (temp 目录) + integrity ok
- 0 字节备份产物触发 raise (不再静默成功)
- 三库备份 (warm/cold) + manifest + 每族保留策略
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from backend.config import config
from backend.services import backup_service
from backend.services.backup_service import (
    INCREMENTAL_BIN_MAGIC,
    _read_wal_pages_since,
    _wal_checksum,
    apply_incremental_chain,
    backup_database,
    backup_incremental,
    backup_side_dbs,
    parse_incremental_bin,
    restore_from_incremental_chain,
)


@pytest.fixture
def db_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """隔离的 db/backups/warm/cold 路径 (不触碰真实 backend/hotspot.db)。"""
    backups = tmp_path / "backups"
    db = tmp_path / "hot.db"
    monkeypatch.setattr(config, "backup_dir", backups)
    monkeypatch.setattr(config, "db_path", db)
    monkeypatch.setattr(config, "warm_db_path", tmp_path / "warm.db")
    monkeypatch.setattr(config, "cold_db_path", tmp_path / "cold.db")
    return db


def _make_db(path: Path, rows: int = 1) -> sqlite3.Connection:
    """WAL 模式建库; 返回持连接 (不 close — close 最后一个连接会 checkpoint 清 WAL)。"""
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    for i in range(rows):
        conn.execute(f"INSERT INTO t VALUES ({i}, 'row{i}')")
    conn.commit()
    return conn


def _build_wal_bytes(
    frames: list[tuple[int, int, bytes]],
    byte3: int = 0x82,
    seq: int = 7,
    corrupt: str | None = None,
) -> bytes:
    """构造 WAL 字节串 (规范累积 checksum, 与真实 SQLite 写出格式一致)。

    frames: [(pgno, commit_size, page_data)]; corrupt: checksum | header |
    truncate | pgno0 (分别破坏末帧校验和 / 头校验和 / 截断末帧页数据 / 末帧页号)。
    """
    big = byte3 == 0x15
    salt = b"\x11" * 4 + b"\x22" * 4
    header = b"\x37\x7f\x06" + bytes([byte3])
    header += (3007000).to_bytes(4, "big")
    header += (4096).to_bytes(4, "big")
    header += seq.to_bytes(4, "big")
    header += salt
    s0, s1 = _wal_checksum(header, 0, 0, big)  # 覆盖前 24 字节 (当前长度恰为 24)
    if corrupt == "header":
        s0 ^= 0xFF
    header += s0.to_bytes(4, "big") + s1.to_bytes(4, "big")

    body = b""
    n = len(frames)
    for idx, (pgno, commit_size, page) in enumerate(frames):
        this_pgno = 0 if (corrupt == "pgno0" and idx == n - 1) else pgno
        fh = this_pgno.to_bytes(4, "big") + commit_size.to_bytes(4, "big") + salt
        c0, c1 = _wal_checksum(fh[:8] + page, s0, s1, big)
        if corrupt == "checksum" and idx == n - 1:
            # 模拟覆写中/撕裂: 数据与已写入的校验和不一致 (校验和按原页算)
            page = bytes([page[0] ^ 0xFF]) + page[1:]
        fh += c0.to_bytes(4, "big") + c1.to_bytes(4, "big")
        s0, s1 = c0, c1
        body += fh + page
    wal = header + body
    if corrupt == "truncate":
        wal = wal[:-100]  # 截掉末帧页数据尾部
    return wal


def _write_wal(db: Path, wal_bytes: bytes) -> None:
    db.with_name(db.name + "-wal").write_bytes(wal_bytes)


# ---------------------------------------------------------------------------
# ① WAL 头校验: 两种字节序都接受
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("byte3", [0x15, 0x82])
def test_wal_header_accepts_both_checksum_byte_orders(db_env, byte3: int) -> None:
    """P0-C: magic 只有前 3 字节固定, 第 4 字节是 checksum 字节序 (本机实测 0x82)。

    用多帧序列同时验证: 头校验和 + 逐帧累积校验和跨帧传递, 两种 word 字序都对。
    """
    db_env.touch()
    frames = [(1, 0, b"A" * 4096), (2, 0, b"B" * 4096), (3, 2, b"C" * 4096)]
    _write_wal(db_env, _build_wal_bytes(frames, byte3=byte3))
    seq, pages, page_size = _read_wal_pages_since(0)
    assert seq == 7
    assert page_size == 4096
    assert pages == [(1, b"A" * 4096), (2, b"B" * 4096), (3, b"C" * 4096)]


def test_wal_header_rejects_bad_magic(db_env) -> None:
    db_env.touch()
    _write_wal(db_env, _build_wal_bytes([(1, 1, b"P" * 4096)], byte3=0x00))
    seq, pages, _ = _read_wal_pages_since(0)
    assert pages == []
    assert seq == 0


# ---------------------------------------------------------------------------
# ①b 撕裂 / 覆写中 / 回滚残留帧 → 累积 checksum 拒收 (P0-C 残余修复)
# ---------------------------------------------------------------------------
def test_wal_stops_at_frame_with_bad_checksum(db_env) -> None:
    """末帧页数据被破坏 (覆写中/撕裂) → 只收前面的有效帧, 不写入 .bin。"""
    db_env.touch()
    frames = [(1, 1, b"A" * 4096), (2, 1, b"B" * 4096), (3, 1, b"C" * 4096)]
    _write_wal(db_env, _build_wal_bytes(frames, corrupt="checksum"))
    _, pages, _ = _read_wal_pages_since(0)
    assert pages == [(1, b"A" * 4096), (2, b"B" * 4096)]


def test_wal_stops_at_truncated_frame(db_env) -> None:
    """末帧页数据截断 (半写入) → 停在最后一个完整有效帧。"""
    db_env.touch()
    frames = [(1, 1, b"A" * 4096), (2, 1, b"B" * 4096)]
    _write_wal(db_env, _build_wal_bytes(frames, corrupt="truncate"))
    _, pages, _ = _read_wal_pages_since(0)
    assert pages == [(1, b"A" * 4096)]


def test_wal_empty_when_header_checksum_bad(db_env) -> None:
    """WAL 头校验和坏 → 整个 WAL 视为空 (标准读取器行为), 0 有效帧走告警路径。"""
    db_env.touch()
    _write_wal(db_env, _build_wal_bytes([(1, 1, b"A" * 4096)], corrupt="header"))
    _, pages, _ = _read_wal_pages_since(0)
    assert pages == []


def test_wal_stops_at_zero_page_number_frame(db_env) -> None:
    """pgno=0 的帧无效 (walDecodeFrame 语义) → 停在其前。"""
    db_env.touch()
    frames = [(1, 1, b"A" * 4096), (2, 1, b"B" * 4096)]
    _write_wal(db_env, _build_wal_bytes(frames, corrupt="pgno0"))
    _, pages, _ = _read_wal_pages_since(0)
    assert pages == [(1, b"A" * 4096)]


def test_real_sqlite_wal_frames_all_valid(db_env) -> None:
    """真实 SQLite 写出的 WAL (非合成): 全部帧必须通过累积 checksum 校验。

    两个事务 (建表+多行 / 单行) → WAL 含 ≥3 帧; 撕裂帧拒收逻辑不得误杀合法帧。
    """
    conn = _make_db(db_env, rows=10)
    conn.execute("INSERT INTO t VALUES (999, 'tx2')")
    conn.commit()
    _, pages, page_size = _read_wal_pages_since(0)
    conn.close()
    assert pages, "real WAL must yield frames"
    assert all(len(page) == page_size for _, page in pages)
    assert page_size == 4096


# ---------------------------------------------------------------------------
# ② 增量产物非空 (v2 自描述格式)
# ---------------------------------------------------------------------------
def test_incremental_artifact_non_empty(db_env) -> None:
    """P0-C: 旧实现 WAL magic 判断恒假 → .bin 恒 0 字节但 job 报成功。"""
    conn = _make_db(db_env)
    try:
        result = backup_incremental()
    finally:
        conn.close()
    bin_path = Path(result["path"])
    assert bin_path.stat().st_size > 0
    data = bin_path.read_bytes()
    assert data[:4] == INCREMENTAL_BIN_MAGIC
    page_size, pages = parse_incremental_bin(data)
    assert page_size == 4096
    assert result["pages"] >= 1
    assert result["pages"] == len(pages)
    # chain.meta 带页数字段 (第 4 列), 可被回读
    meta = (bin_path.parent / "chain.meta").read_text().split()
    assert int(meta[3]) == len(pages)


def test_incremental_without_wal_still_writes_header(db_env) -> None:
    """无 WAL 时产出 8 字节 header (0 页), 不再静默空文件。"""
    sqlite3.connect(str(db_env)).close()  # 空库, 无 WAL
    result = backup_incremental()
    data = Path(result["path"]).read_bytes()
    assert data[:4] == INCREMENTAL_BIN_MAGIC
    assert result["pages"] == 0


# ---------------------------------------------------------------------------
# ③ 恢复演练: temp 目录真写页 + integrity ok
# ---------------------------------------------------------------------------
def test_restore_from_incremental_chain_real_write(
    db_env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """base full + 增量链恢复到独立目标: WAL 里 commit 的行必须真的出现。"""
    conn = _make_db(db_env)
    full = backup_database()  # base 快照 (此时只有 row0)
    conn.execute("INSERT INTO t VALUES (99, 'wal_only')")
    conn.commit()
    inc = backup_incremental()  # 抓 WAL 帧 (含 row99 的页)
    conn.close()
    assert inc["pages"] >= 1

    target = tmp_path / "restored.db"
    monkeypatch.setattr(config, "db_path", target)
    result = restore_from_incremental_chain(Path(full["path"]))

    assert result["ok"] is True, result
    assert result["applied_pages"] >= 1
    assert result["integrity_check"] == "ok"

    verify = sqlite3.connect(str(target))
    try:
        rows = dict(verify.execute("SELECT id, v FROM t").fetchall())
    finally:
        verify.close()
    assert rows[0] == "row0"       # 来自 base
    assert rows[99] == "wal_only"  # 只存在于增量链 → 证明真写页


def test_apply_incremental_chain_on_temp_copy(db_env, tmp_path: Path) -> None:
    """check_backup_chain 同款路径: full 副本 + apply_incremental_chain → ok。"""
    conn = _make_db(db_env, rows=50)  # 多行 → 多页, 验 seek 定位正确
    full = backup_database()
    conn.execute("UPDATE t SET v = 'updated' WHERE id = 3")
    conn.execute("INSERT INTO t VALUES (1000, 'tail')")
    conn.commit()
    inc = backup_incremental()
    conn.close()

    target = tmp_path / "copy.db"
    shutil.copy2(Path(full["path"]), target)
    chain = sorted(Path(inc["path"]).parent.glob("wal-*.bin"))
    result = apply_incremental_chain(target, chain)
    assert result["ok"] is True, result
    assert result["integrity_check"] == "ok"

    verify = sqlite3.connect(str(target))
    try:
        assert verify.execute("SELECT v FROM t WHERE id=3").fetchone()[0] == "updated"
        assert verify.execute("SELECT v FROM t WHERE id=1000").fetchone()[0] == "tail"
    finally:
        verify.close()


def test_restore_rejects_corrupt_chain(
    db_env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """坏链文件 (0 字节) → ok=False, 不假报成功。"""
    db_env.touch()
    full = backup_database()
    chain_dir = Path(config.backup_dir) / "incremental"
    chain_dir.mkdir(parents=True)
    (chain_dir / "wal-bad-0001.bin").write_bytes(b"")  # 0 字节
    monkeypatch.setattr(config, "db_path", tmp_path / "out.db")
    result = restore_from_incremental_chain(Path(full["path"]), chain_dir)
    assert result["ok"] is False
    assert "error" in result


# ---------------------------------------------------------------------------
# ④ 0 字节产物触发告警 (raise, 不静默成功)
# ---------------------------------------------------------------------------
class _ZeroBackupConn:
    """假 sqlite 连接: backup() no-op → dst 保持 0 字节。"""

    def backup(self, other: object) -> None:
        pass

    def commit(self) -> None:
        pass

    def close(self) -> None:
        pass


def test_zero_byte_backup_artifact_raises(db_env, monkeypatch: pytest.MonkeyPatch) -> None:
    """P0-C: 备份产物 0 字节必须 raise, 不允许 job 静默报成功。"""
    Path(config.warm_db_path).touch()  # warm 源存在

    def _fake_connect(path: str) -> _ZeroBackupConn:
        Path(path).touch()  # sqlite3.connect 会建空文件, backup no-op → 保持 0 字节
        return _ZeroBackupConn()

    monkeypatch.setattr(backup_service.sqlite3, "connect", _fake_connect)
    with pytest.raises(RuntimeError, match="0 bytes"):
        backup_side_dbs("test-zero")


# ---------------------------------------------------------------------------
# 三库备份 + manifest + 每族保留策略
# ---------------------------------------------------------------------------
def test_side_dbs_backup_manifest_and_retention(db_env) -> None:
    """warm/cold 各走 Connection.backup + sha256 旁车; manifest 落盘; 每族留 3 份。"""
    # cold 建一次空库 (存在即备份); warm 每轮写一行
    sqlite3.connect(str(Path(config.cold_db_path))).close()
    for i in range(4):
        warm = Path(config.warm_db_path)
        conn = sqlite3.connect(str(warm))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE IF NOT EXISTS w (v TEXT)")
        conn.execute(f"INSERT INTO w VALUES ('gen{i}')")
        conn.commit()
        conn.close()
        entries = backup_side_dbs(f"20260912_0{4 + i}0000")

    assert len(entries) == 2
    assert {e["kind"] for e in entries} == {"warm", "cold"}
    backups = Path(config.backup_dir)
    # 每族只留 BACKUP_RETENTION=3 份
    assert len(list(backups.glob("hotspot-warm-*.db"))) == backup_service.BACKUP_RETENTION
    assert len(list(backups.glob("hotspot-cold-*.db"))) == backup_service.BACKUP_RETENTION
    # sha256 旁车可复算
    for e in entries:
        assert hashlib.sha256(Path(e["path"]).read_bytes()).hexdigest() == e["sha256"]
    # manifest 覆盖 warm+cold
    manifests = sorted(backups.glob("backup-manifest-*.json"))
    assert manifests
    data = json.loads(manifests[-1].read_text())
    assert {d["kind"] for d in data["dbs"]} == {"warm", "cold"}


def test_full_backup_covers_three_dbs_and_hot_retention(db_env) -> None:
    """backup_database: manifest 含三库 + hot sha256 旁车; 保留 glob 不误删 warm/cold。"""
    sqlite3.connect(str(Path(config.warm_db_path))).close()
    sqlite3.connect(str(Path(config.cold_db_path))).close()

    conn = _make_db(db_env)
    full = backup_database()
    conn.close()

    assert full["mode"] == "full"
    assert {d["kind"] for d in full["dbs"]} == {"hot", "warm", "cold"}
    backups = Path(config.backup_dir)
    assert Path(f"{full['path']}.sha256").exists()
    # manifest 存在且含三库
    manifests = sorted(backups.glob("backup-manifest-*.json"))
    assert manifests
    data = json.loads(manifests[-1].read_text())
    assert {d["kind"] for d in data["dbs"]} == {"hot", "warm", "cold"}
    # hot 族 glob 收紧为 [0-9] 开头: warm/cold 备份不会被 hot 保留策略匹配
    assert list(backups.glob("hotspot-[0-9]*.db")) == [Path(full["path"])]
