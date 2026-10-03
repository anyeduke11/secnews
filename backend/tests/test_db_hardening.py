"""DB 路径锚定 + 权限位回归 — v0.8.6 P0-9 / 审计 F0-12 (R6)。

F0-12a: ``HOTSPOT_DB_PATH`` 相对路径此前按启动 CWD 解析 — 换目录启动
打开全新空库却 ATTACH 真实 warm 库 (磁盘上 0 字节 data/hotspot.db 为证)。
修复: Settings 全部磁盘路径字段锚定仓库根 (绝对路径原样)。

F0-12b: 库文件与备份产物默认 0644 (含 llm_secrets 密文与全量 wiki 正文,
同机任意进程可读)。修复: get_connection 首连收紧 0600 (含 -wal/-shm 边车),
备份链全部产物落盘即 0600。

审计验收: "换 CWD 启动仍打开同一库" + 库/备份 0600。
"""
from __future__ import annotations

import os
import sqlite3
import stat
from pathlib import Path

import pytest

from backend.config import BASE_DIR, Settings
from backend.repository import db as db_mod
from backend.services import backup_service


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


# ---------------------------------------------------------------------------
# F0-12a — 相对路径锚定仓库根, CWD 无关
# ---------------------------------------------------------------------------
class TestPathAnchoring:
    def test_relative_db_path_anchored_to_repo_root(self, monkeypatch):
        """相对路径 → 仓库根下的绝对路径 (而非 CWD 相对)。"""
        monkeypatch.chdir("/")  # 极端 CWD: 锚定前会解析成 /data/x.db
        s = Settings(db_path="data/x.db", _env_file=None)
        assert s.db_path.is_absolute()
        assert s.db_path == BASE_DIR.parent / "data" / "x.db"

    def test_same_db_across_cwd(self, tmp_path, monkeypatch):
        """审计验收主断言: 换 CWD 构造 Settings, 同一相对 env 解析到同一文件。"""
        monkeypatch.setenv("HOTSPOT_DB_PATH", "data/hotspot.db")
        monkeypatch.chdir(tmp_path)
        s1 = Settings(_env_file=None)
        monkeypatch.chdir("/")  # 换启动目录
        s2 = Settings(_env_file=None)
        assert s1.db_path == s2.db_path
        assert s1.db_path == BASE_DIR.parent / "data" / "hotspot.db"

    def test_absolute_path_untouched(self, tmp_path):
        """绝对路径原样保留 (conftest 测试隔离依赖此语义)。"""
        p = tmp_path / "iso.db"
        s = Settings(db_path=str(p), _env_file=None)
        assert s.db_path == p

    def test_warm_cold_also_anchored(self):
        """warm/cold 相对路径同锚定 — 防 main 相对/warm 绝对的混搭分裂。"""
        s = Settings(
            warm_db_path="w/x.db", cold_db_path="c/x.db", _env_file=None
        )
        assert s.warm_db_path == BASE_DIR.parent / "w" / "x.db"
        assert s.cold_db_path == BASE_DIR.parent / "c" / "x.db"


# ---------------------------------------------------------------------------
# F0-12b — 库文件与备份产物 0600
# ---------------------------------------------------------------------------
@pytest.fixture
def iso_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """隔离 get_connection 的三库路径 (不触碰真实库)。"""
    from backend.config import config

    monkeypatch.setattr(config, "db_path", tmp_path / "hot.db")
    monkeypatch.setattr(config, "warm_db_path", tmp_path / "warm.db")
    monkeypatch.setattr(config, "cold_db_path", tmp_path / "cold.db")
    return tmp_path / "hot.db"


class TestDbFilePermissions:
    def test_get_connection_chmods_existing_0644_to_0600(self, iso_db):
        """审计修复主断言: 0644 存量库文件在首连时被收紧为 0600。"""
        iso_db.parent.mkdir(parents=True, exist_ok=True)
        sqlite3.connect(str(iso_db)).close()  # 创建文件
        os.chmod(iso_db, 0o644)  # 模拟审计发现的存量 0644
        assert _mode(iso_db) == 0o644

        # conftest autouse fixture 可能在本线程已缓存连接 (thread-local),
        # 先清缓存确保走"首连"路径 (open + chmod)
        db_mod.close_db()
        try:
            conn = db_mod.get_connection()
            assert conn is not None
            assert _mode(iso_db) == 0o600
        finally:
            db_mod.close_db()

    def test_wal_sidecar_secured(self, iso_db):
        """-wal 边车 (承载活数据页) 一并收紧。"""
        db_mod.close_db()
        try:
            conn = db_mod.get_connection()
            conn.execute("CREATE TABLE IF NOT EXISTS t (x)")
            wal = iso_db.with_name(iso_db.name + "-wal")
            if wal.exists():  # WAL 在首写后才落盘
                assert _mode(wal) == 0o600
        finally:
            db_mod.close_db()


class TestBackupArtifactPermissions:
    @pytest.fixture
    def backup_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        from backend.config import config

        db = tmp_path / "hot.db"
        c = sqlite3.connect(str(db))
        c.execute("CREATE TABLE t (v)")
        c.execute("INSERT INTO t VALUES ('x')")
        c.commit()
        c.close()
        monkeypatch.setattr(config, "backup_dir", tmp_path / "backups")
        monkeypatch.setattr(config, "db_path", db)
        monkeypatch.setattr(config, "warm_db_path", tmp_path / "warm.db")
        monkeypatch.setattr(config, "cold_db_path", tmp_path / "cold.db")
        return tmp_path / "backups"

    def test_backup_database_artifacts_0600(self, backup_env):
        """全量备份链产物 (.db 快照 / .sha256) 落盘即 0600。"""
        backup_service.backup_database()
        artifacts = list(backup_env.glob("*.db")) + list(
            backup_env.glob("*.sha256")
        )
        assert artifacts, "备份产物缺失 — 测试自身失效"
        for f in artifacts:
            assert _mode(f) == 0o600, f"{f.name} 权限 {_mode(f):o}"

    def test_incremental_chain_0600(self, backup_env):
        """增量链 .bin + .sha256 同密级。"""
        backup_service.backup_incremental()
        inc_dir = backup_env / backup_service.INCREMENTAL_DIR
        bins = list(inc_dir.glob("*.bin")) + list(inc_dir.glob("*.sha256"))
        assert bins
        for f in bins:
            assert _mode(f) == 0o600, f"{f.name} 权限 {_mode(f):o}"
