"""v0.8.2 Y-A4 — 备份完整性校验测试 (CRITICAL_REVIEW §2.4)。

校验链: PRAGMA integrity_check + 核心表行数单调性 (备份 ≤ 实时) +
audit_log append-only 抽样 + knowledge zip; 失败 audit_log 留痕。
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.services.backup_verify_service import (
    CORE_TABLES,
    verify_latest_backup,
)


@pytest.fixture
def backup_env(temp_db, monkeypatch, tmp_path):
    """temp_db (完整 schema) + 私有 backups/ 目录。"""
    backups = tmp_path / "backups"
    backups.mkdir()
    monkeypatch.setattr("backend.config.config.backup_dir", backups)
    yield backups


def _make_full_backup():
    from backend.services.backup_service import backup_database

    return backup_database()


class TestVerifyLatestBackup:
    def test_no_backup_reports_error(self, backup_env):
        report = verify_latest_backup()
        assert report["ok"] is False
        assert any("未找到" in e for e in report["errors"])

    def test_good_backup_passes(self, backup_env):
        result = _make_full_backup()
        report = verify_latest_backup()
        assert report["ok"] is True, report["errors"]
        assert report["integrity_check"] == "ok"
        assert report["backup_path"] == result["path"]
        for t in CORE_TABLES:
            assert report["tables"][t]["backup"] >= 0
            assert report["tables"][t]["backup"] <= report["tables"][t]["live"]

    def test_corrupt_backup_fails(self, backup_env):
        _make_full_backup()
        # 备份文件覆盖为垃圾字节 → 页级损坏
        backup_path = verify_latest_backup()["backup_path"]
        with open(backup_path, "wb") as f:
            f.write(b"garbage-not-sqlite" * 100)
        report = verify_latest_backup()
        assert report["ok"] is False
        assert report["errors"], "损坏必须产生 errors"

    def test_live_shrinking_detected(self, backup_env):
        """备份后实时库被清表 → 行数单调性报警 (恢复了错误文件的信号)。"""
        # 先写审计行 (新库 audit_log 为空, 无从对比单调性)
        from backend.observability_records import record_audit

        for i in range(3):
            record_audit(actor="t", action="verify_test", target=f"row-{i}", detail={})
        _make_full_backup()
        conn = sqlite3.connect(str(backup_env.parent / "test.db"))
        try:
            conn.execute("DELETE FROM audit_log")
            conn.commit()
        finally:
            conn.close()
        report = verify_latest_backup()
        assert report["ok"] is False
        assert any("audit_log" in e for e in report["errors"])

    def test_never_raises_on_unexpected(self, backup_env, monkeypatch):
        """灾难检查自身不能炸 — 内部异常 → ok=False 报告。"""
        monkeypatch.setattr(
            "backend.services.backup_verify_service._latest_backup",
            lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        report = verify_latest_backup()
        assert report["ok"] is False
        assert any("crashed" in e for e in report["errors"])

    def test_verify_never_throws(self, backup_env):
        _make_full_backup()
        report = verify_latest_backup()
        assert isinstance(report, dict)


class TestBackupVerifyJob:
    def test_job_ok_passes(self, backup_env, caplog):
        """ok 报告 → job 正常返回。"""
        import asyncio

        from backend.scheduler.jobs.maintenance import backup_verify_job

        _make_full_backup()
        asyncio.run(backup_verify_job())

    def test_job_failure_raises_for_instrument(self, backup_env, monkeypatch):
        """校验失败 → RuntimeError (instrument_job 标 ok=False)。"""
        import asyncio

        import pytest

        from backend.scheduler.jobs import maintenance

        monkeypatch.setattr(
            "backend.services.backup_verify_service.verify_latest_backup",
            lambda: {"ok": False, "errors": ["integrity_check=fail"], "backup_path": None},
        )
        with pytest.raises(RuntimeError):
            asyncio.run(maintenance.backup_verify_job())
