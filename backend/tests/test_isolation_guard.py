"""v1.0 T01 — 测试隔离哨兵验证 (conftest 会话隔离 + 生产路径审计守卫)。

验证三件事 (EXECUTION_GUIDE T01 通过证据):
1. 隔离生效: config 三库/日志/备份/data 与 Wiki 根全部落在会话临时根
   (新手验收: 测试数据写到了哪个临时目录 — 本文件打印并断言);
2. 哨兵拒绝: 生产数据根的 sqlite 连接 / 文件写入 / 出网 socket 被守卫拦截;
3. 隔离根可用: 会话根库已 init_db, 写入可正常落库 (正常路径)。
"""

from __future__ import annotations

import os
import sqlite3

import pytest

from backend.tests.conftest import (
    _ISOLATION_GUARDED,
    _ISOLATION_ROOT,
    _REPO_ROOT,
)


@pytest.mark.skipif(
    not _ISOLATION_GUARDED, reason="HOTSPOT_TEST_UNGUARDED=1 时守卫关闭"
)
class TestIsolationActive:
    def test_data_roots_inside_session_root(self):
        """隔离断言: 数据根在会话临时根内, 不在仓库真实位置。

        warm/cold 例外: autouse _isolate_temp_dbs 每测把它们指到 pytest
        tmp_path (比会话根更强的隔离) — 同样安全, 断言接受两种落点。
        """
        from backend.config import config
        from backend.wiki_fs.paths import wiki_root

        root = str(_ISOLATION_ROOT) + os.sep
        strict = (
            ("db_path", config.db_path),
            ("log_dir", config.log_dir),
            ("backup_dir", config.backup_dir),
            ("data_dir", config.data_dir),
        )
        for name, p in strict:
            assert str(p).startswith(root), f"{name}={p} 未隔离"
            assert not str(p).startswith(str(_REPO_ROOT)), (
                f"{name}={p} 指向仓库真实路径"
            )
        # warm/cold/wiki 例外: autouse _isolate_temp_dbs / _isolate_knowledge_dirs
        # 每测把它们指到 pytest tmp_path (比会话根更强的既有隔离) — 接受两种落点。
        for name, p in (
            ("warm_db_path", config.warm_db_path),
            ("cold_db_path", config.cold_db_path),
            ("wiki_root", wiki_root()),
        ):
            assert "hotspot-test-iso-" in str(p) or "pytest-of-" in str(p), (
                f"{name}={p} 既不在会话根也不在 pytest tmp"
            )
            assert not str(p).startswith(str(_REPO_ROOT)), (
                f"{name}={p} 指向仓库真实路径"
            )

    def test_session_root_is_printed_for_acceptance(self, capsys):
        """新手验收证据: 测试数据写到哪个临时目录 (路径同时进 stdout 供检查)。"""
        print(f"\n[T01] 本测试会话的隔离数据根: {_ISOLATION_ROOT}")
        assert _ISOLATION_ROOT.exists()
        assert (str(_ISOLATION_ROOT)).startswith("/var/folders/") or str(
            _ISOLATION_ROOT
        ).startswith("/tmp")

    def test_session_root_db_has_schema(self, temp_db):
        """会话根库经 init_db 有 schema; temp_db 测试照常工作 (正常路径)。"""
        from backend.repository.db import get_connection

        conn = get_connection()
        n = conn.execute("SELECT count(*) FROM settings").fetchone()[0]
        assert n >= 0


@pytest.mark.skipif(
    not _ISOLATION_GUARDED, reason="HOTSPOT_TEST_UNGUARDED=1 时守卫关闭"
)
class TestSentinelRejectsProductionPaths:
    def test_sqlite_connect_to_real_db_rejected(self):
        """哨兵失败路径: sqlite 连接真实 HOT 库必须被守卫拒绝。"""
        real_db = _REPO_ROOT / "backend" / "hotspot.db"
        assert real_db.exists(), "哨兵前提: 真实库应存在"
        with pytest.raises(AssertionError, match="隔离守卫"):
            sqlite3.connect(str(real_db))

    def test_sqlite_connect_real_db_string_path_rejected(self):
        """相对路径绕过也被拒 (abspath 二次检查)。"""
        with pytest.raises(AssertionError, match="隔离守卫"):
            sqlite3.connect("backend/hotspot.db")

    def test_open_write_to_real_wiki_rejected(self):
        """哨兵失败路径: 对真实 Wiki 根的写打开被守卫拒绝。"""
        target = _REPO_ROOT / "llm-wiki-2.0" / "_t01_sentinel_probe.tmp"
        with pytest.raises(AssertionError, match="隔离守卫"):
            with open(target, "w"):
                pass  # pragma: no cover - 守卫应在 open 前拒绝
        assert not target.exists(), "哨兵必须在实际落盘前拦截"

    def test_open_write_to_real_logs_rejected(self):
        target = _REPO_ROOT / "backend" / "logs" / "_t01_sentinel_probe.log"
        with pytest.raises(AssertionError, match="隔离守卫"):
            with open(target, "a"):
                pass  # pragma: no cover
        assert not target.exists()

    def test_read_open_still_allowed(self):
        """正常路径: 读真实源码文件不受影响 (守卫只拦写)。"""
        src = _REPO_ROOT / "backend" / "version.py"
        with open(src) as f:
            assert "APP_VERSION" in f.read()

    def test_outbound_socket_rejected(self):
        """哨兵失败路径: 普通测试默认禁止出网。"""
        import socket

        with pytest.raises(AssertionError, match="禁止出网"):
            sock = socket.socket()
            try:
                sock.connect(("example.com", 80))
            finally:
                sock.close()

    def test_localhost_socket_allowed(self):
        """正常路径: 回环连接放行 (TestClient/portal 等进程内机制不受影响)。"""
        import socket

        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        client = socket.socket()
        try:
            client.connect(("127.0.0.1", port))  # 不 accept, 仅验证 connect 放行
        finally:
            client.close()
            server.close()
