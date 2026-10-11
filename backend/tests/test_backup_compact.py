"""DEV-0323: 备份滚动保留 (1 full + ≤3 增量档, roll-forward 合成) 测试。

测试意图 (Rule 9): 用户模型「只保留一个最新全量 + 3 档增量; 每次清理前用
全量+最旧增量合成第二个全量, 然后去掉最旧的全量」的目标是**不冗余且可恢复**。
本文件的核心断言不是"文件数对不对", 而是合成后 **新 full + 剩余链仍能恢复
出最新状态** (覆盖范围不丢) — 数量 invariant 只是表象, 恢复正确性才是承诺。
构造全部走真实 backup_database()/backup_incremental() (真 WAL 页链)。
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from backend.config import config
from backend.services import backup_service
from backend.services.backup_service import (
    INCREMENTAL_DIR,
    backup_database,
    backup_incremental,
    backup_inventory,
    compact_backup_chain,
    restore_from_incremental_chain,
)

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture
def db_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """隔离 db/backups/warm/cold (与 test_backup_service 同款)。"""
    backups = tmp_path / "backups"
    db = tmp_path / "hot.db"
    monkeypatch.setattr(config, "backup_dir", backups)
    monkeypatch.setattr(config, "db_path", db)
    monkeypatch.setattr(config, "warm_db_path", tmp_path / "warm.db")
    monkeypatch.setattr(config, "cold_db_path", tmp_path / "cold.db")
    return db


def _make_db(path: Path, rows: int = 20) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    for i in range(rows):
        conn.execute("INSERT INTO t VALUES (?, ?)", (i, f"row{i}"))
    conn.commit()
    return conn


def _bins(backups: Path) -> list[Path]:
    return sorted(
        (backups / INCREMENTAL_DIR).glob("wal-*.bin"),
        key=lambda p: p.stat().st_mtime,
    )


def _fulls(backups: Path) -> list[Path]:
    return sorted(
        backups.glob("hotspot-[0-9]*.db"),
        key=lambda p: p.stat().st_mtime,
    )


def _advance_and_backup(conn: sqlite3.Connection, backups: Path, n: int, tag: str) -> None:
    """写新行 → 增量备份; mtime 强制递增 (同秒粒度会让排序断言抖动)。"""
    conn.execute("INSERT INTO t VALUES (?, ?)", (9000 + n, f"{tag}-{n}"))
    conn.commit()
    backup_incremental()
    bins = _bins(backups)
    base = bins[-1].stat().st_mtime
    os.utime(bins[-1], (base + 10 + n, base + 10 + n))  # 拉开档间 mtime


# ---------------------------------------------------------------------------
# ① 不变量: 链超 keep → roll-forward 合成, 数量收口且恢复正确
# ---------------------------------------------------------------------------
def test_compact_absorbs_oldest_and_restore_still_correct(db_env):
    """4 档链触发合成后: 新 full + 剩余 3 档仍能恢复出含全部时刻的数据。

    被 absorb 的最旧档数据已并入新 full (页重放), 恢复点 = 最新状态;
    若合成逻辑丢覆盖 (比如误删未 absorb 的档), 末行数据将缺失。
    """
    backups = Path(config.backup_dir)
    conn = _make_db(db_env)
    full = backup_database()
    for i in range(4):
        _advance_and_backup(conn, backups, i, f"gen{i}")
    # 每次 backup_incremental 尾部都跑 compact: 第 4 档写入即触发吸收,
    # 循环结束后链已自动收口 ≤3 (无 4 档中间稳态)
    conn.execute("INSERT INTO t VALUES (9999, 'final')")
    conn.commit()
    backup_incremental()
    conn.close()

    bins = _bins(backups)
    assert len(bins) <= 3, f"自动收口: 链应 ≤3 档, 实测 {len(bins)}"
    fulls = _fulls(backups)
    assert len(fulls) == 1, f"不变量 1 个 full, 实测 {len(fulls)}"
    assert fulls[0].name != Path(full["path"]).name, "旧 base full 已被合成新 full 取代"
    # 配对产物齐套: sha 旁车 + manifest + knowledge zip
    assert fulls[0].with_suffix(fulls[0].suffix + ".sha256").exists()
    ts = fulls[0].stem.removeprefix("hotspot-")
    assert (backups / f"backup-manifest-{ts}.json").exists()

    # 恢复正确性: 新 full + 剩余链 → 最新状态含所有代数据 (含被 absorb 的)
    target = backups.parent / "restored.db"
    config_db = config.db_path
    config.db_path = target
    try:
        result = restore_from_incremental_chain(fulls[0])
        assert result["ok"] is True, result
        v = sqlite3.connect(str(target))
        try:
            rows = dict(v.execute("SELECT id, v FROM t").fetchall())
        finally:
            v.close()
        assert rows[9999] == "final"
        # 第 0 代 (最先被 absorb 的档写入的行) 必须仍可达
        assert rows[9000] == "gen0-0", "roll-forward 合成不得丢最旧档覆盖"
        assert rows[9003] == "gen3-3"
    finally:
        config.db_path = config_db


# ---------------------------------------------------------------------------
# ② 幂等: 链在限内 no-op
# ---------------------------------------------------------------------------
def test_compact_noop_within_limit(db_env):
    backups = Path(config.backup_dir)
    conn = _make_db(db_env)
    backup_database()
    _advance_and_backup(conn, backups, 0, "x")
    conn.close()
    r = compact_backup_chain(keep_incrementals=3)
    assert r["ok"] is True and r["compacted"] is False
    assert len(_fulls(backups)) == 1 and len(_bins(backups)) == 1


# ---------------------------------------------------------------------------
# ③ 合成失败 → 一切原样 (fail-loud, 绝不删旧 base)
# ---------------------------------------------------------------------------
def test_compact_failure_preserves_everything(db_env):
    backups = Path(config.backup_dir)
    conn = _make_db(db_env)
    full = backup_database()
    old_full = Path(full["path"])
    for i in range(3):
        _advance_and_backup(conn, backups, i, "ok")
    conn.close()
    # 注入坏档 = 0 字节且 mtime 是**活跃链内最旧** (≥ full_mtime, 否则
    # 会被判残档而非 absorb 对象) — absorb 集取最旧超额档, 坏档必须落在
    # absorb 集内才测得到"合成失败零删除"
    bad = backups / INCREMENTAL_DIR / "wal-00000000_000000-9999.bin"
    bad.write_bytes(b"")
    full_mtime = _fulls(backups)[-1].stat().st_mtime
    first_bin_mtime = _bins(backups)[0].stat().st_mtime
    os.utime(bad, ((full_mtime + first_bin_mtime) / 2,) * 2)

    r = compact_backup_chain(keep_incrementals=3)
    assert r["ok"] is False and "failed" in (r["error"] or "")
    # 关键: 失败路径零删除
    assert old_full.exists(), "合成失败不得删旧 full"
    assert bad.exists()
    assert len(_bins(backups)) == 4

    # 且后续增量备份的自动 compact 同样不破坏既有 base
    assert len(_fulls(backups)) == 1


# ---------------------------------------------------------------------------
# ④ 旧 full 超额 / 残档 / knowledge-inc 超额清理
# ---------------------------------------------------------------------------
def test_compact_cleans_extra_fulls_stale_bins_and_zips(db_env):
    backups = Path(config.backup_dir)
    conn = _make_db(db_env)
    backup_database()
    _advance_and_backup(conn, backups, 0, "y")
    conn.close()
    keep = _fulls(backups)[-1]

    # 造两个更旧的假 full (mtime 早于 keep) + 配对 zip/manifest
    for name, age in (("hotspot-20200101_000000.db", 900),
                      ("hotspot-20200102_000000.db", 800)):
        p = backups / name
        p.write_bytes(b"x" * 512)
        p.with_suffix(".knowledge.zip").write_bytes(b"PK")
        os.utime(p, (keep.stat().st_mtime - age,) * 2)
    # 残档: mtime 早于 full
    stale_bin = backups / INCREMENTAL_DIR / "wal-20200101_000000-0000.bin"
    stale_bin.write_bytes(b"x" * 16)
    os.utime(stale_bin, (keep.stat().st_mtime - 700,) * 2)
    # knowledge-inc 5 份
    for i in range(5):
        z = backups / f"knowledge-inc-202601{20 + i}_000000.zip"
        z.write_bytes(b"PK" * 8)
        z_stat = z.stat()
        os.utime(z, (z_stat.st_atime, z_stat.st_mtime))
    # 孤儿 paired zip: 主体 full 不存在 (旧轮转/手删残留, 生产实测存在此案)
    orphan = backups / "hotspot-20190101_000000.knowledge.zip"
    orphan.write_bytes(b"PK" * 8)

    r = compact_backup_chain(keep_incrementals=3)
    assert r["ok"] is True
    assert len(_fulls(backups)) == 1, "不变量: 只留最新 full"
    assert (backups / "hotspot-20200101_000000.knowledge.zip").exists() is False
    assert not orphan.exists(), "孤儿 paired zip 应随 compact 清掉"
    assert not stale_bin.exists(), "早于 full 的残档应清 (checker 本就排除)"
    assert len(list(backups.glob("knowledge-inc-*.zip"))) == backup_service.KNOWLEDGE_INC_KEEP


# ---------------------------------------------------------------------------
# ⑤ 无 full → 如实失败
# ---------------------------------------------------------------------------
def test_compact_without_full_fails_honestly(db_env):
    r = compact_backup_chain(keep_incrementals=3)
    assert r["ok"] is False
    assert "no HOT full" in (r["error"] or "")


# ---------------------------------------------------------------------------
# ⑥ inventory 形状 (= /maint 备份卡契约) + 真实数字
# ---------------------------------------------------------------------------
def test_backup_inventory_shape(db_env):
    backups = Path(config.backup_dir)
    conn = _make_db(db_env, rows=30)
    backup_database()
    _advance_and_backup(conn, backups, 0, "inv")
    conn.close()

    inv = backup_inventory()
    assert inv["policy"]["full_keep"] == 1
    assert inv["policy"]["incremental_keep"] == 3
    assert len(inv["fulls"]) == 1
    f0 = inv["fulls"][0]
    assert {"name", "size_mb", "age_hours"} <= set(f0) and f0["size_mb"] >= 0
    assert inv["chain"]["count"] == len(inv["chain"]["files"]) == 1
    b0 = inv["chain"]["files"][0]
    assert {"name", "size_kb", "pages", "age_hours"} <= set(b0)
    assert b0["pages"] >= 1, "真实链应解析出页数 (header 8B + 记录)"
    assert inv["totals"]["mb"] >= 0  # 小库 round 后可能 0.0 (非缺陷)
    assert isinstance(inv["side_dbs"]["warm"], int)


# ---------------------------------------------------------------------------
# ⑦ verify glob 回归守卫: "最新 full" 不得被 warm/cold 侧库冒充
# ---------------------------------------------------------------------------
def test_verify_latest_target_is_hot_full(db_env):
    """旧 glob `hotspot-*.db` 会命中 mtime 更新的 hotspot-warm-*.db →
    verify 对着缺 hotspots 表的 WARM 库假报 ok (第四起想象契约同族 bug)。"""
    from backend.services.backup_verify_service import _latest_backup

    backups = Path(config.backup_dir)
    conn = _make_db(db_env)
    full = backup_database()
    conn.close()
    fake_warm = backups / "hotspot-warm-20990101_000000.db"
    fake_warm.touch()  # mtime 最新
    picked = _latest_backup()
    assert picked is not None and Path(picked).name == Path(full["path"]).name, (
        f"应选 HOT full, 实测 {picked}"
    )
