"""v0.7 Batch ⑨ B9-2: secrets 主密钥轮换检查 job + audit + cooldown tests."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.repository.db import get_connection


@pytest.fixture
def _setup_master_key(temp_db):
    """临时 db 上创建主密钥, last_rotated_at 设为 100 天前 → should_rotate=True."""
    from datetime import datetime, timedelta, timezone

    from backend.repository.db import get_connection
    from backend.repository.encryption_keys_repo import EncryptionKeyRepository

    ek = EncryptionKeyRepository()
    ek.setup_default(master_key="test-master-key-12345678", role="admin")
    # 把 last_rotated_at 改为 100 天前 (走 repo 接口 + 直接 SQL UPDATE)
    old = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    get_connection().execute(
        "UPDATE encryption_keys SET last_rotated_at = ? WHERE role = 'admin'",
        (old,),
    )


@pytest.mark.asyncio
async def test_rotation_check_job_skips_when_no_setup(temp_db, monkeypatch):
    """未设主密钥时 should_rotate=False, job 静默 return."""
    from backend.scheduler.jobs.security import secrets_rotation_check_job

    # 不创建 master key, 也不 mock SecretsService; 真实走 path
    with patch(
        "backend.services.secrets_service.SecretsService.rotation_status",
        return_value={"setup": False, "should_rotate": False},
    ):
        await secrets_rotation_check_job()  # 不抛 = 成功


@pytest.mark.asyncio
async def test_rotation_check_job_dispatches_and_audits(temp_db, _setup_master_key, monkeypatch):
    """已设主密钥 + age >= 阈值 → 调 dispatch + 落 audit + 写 cooldown settings."""
    from backend.repository.settings_repo import SettingsRepository
    from backend.scheduler.jobs.security import secrets_rotation_check_job

    # mock dispatch 避免真发通道
    captured: dict = {}

    async def fake_dispatch(payload, alert_id=None):
        captured["metric"] = payload.metric
        captured["detail"] = payload.detail
        captured["value"] = payload.value
        captured["threshold"] = payload.threshold

    # dispatch 在 job 内 function-local import, monkeypatch 实际模块属性 (alert_dispatcher.dispatch)
    # 即可 — Python 解析 function-local `from ... import dispatch` 时按 module.attr 查找
    monkeypatch.setattr("backend.services.alert_dispatcher.dispatch", fake_dispatch)
    # 清 cooldown
    SettingsRepository().set("secrets.rotation.last_notified_at", "")

    await secrets_rotation_check_job()

    assert captured.get("metric") == "secrets.rotation_age_days"
    assert "Secrets 主密钥" in captured.get("detail", {}).get("title", "")
    assert captured.get("value", 0) >= 90
    assert captured.get("threshold", 0) == 90
    # audit 落了
    row = get_connection().execute(
        "SELECT detail FROM audit_log WHERE action = 'secrets.rotation_reminded' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    # cooldown 落 settings
    assert SettingsRepository().get("secrets.rotation.last_notified_at", None) is not None


@pytest.mark.asyncio
async def test_rotation_check_job_cooldown_blocks_resend(temp_db, _setup_master_key, monkeypatch):
    """同一天已通知 → 跳过 dispatch."""
    from datetime import datetime, timezone

    from backend.repository.settings_repo import SettingsRepository
    from backend.scheduler.jobs.security import secrets_rotation_check_job

    today = datetime.now(timezone.utc).date().isoformat()
    SettingsRepository().set("secrets.rotation.last_notified_at", today)

    called = []

    async def fake_dispatch(payload, alert_id=None):
        called.append(payload)

    monkeypatch.setattr("backend.services.alert_dispatcher.dispatch", fake_dispatch)
    await secrets_rotation_check_job()
    assert called == []


@pytest.mark.asyncio
async def test_rotation_check_job_should_rotate_false(temp_db, _setup_master_key, monkeypatch):
    """age < remind_days → should_rotate=False, 不调 dispatch."""
    from backend.scheduler.jobs.security import secrets_rotation_check_job

    called = []

    async def fake_dispatch(payload, alert_id=None):
        called.append(payload)

    monkeypatch.setattr("backend.services.alert_dispatcher.dispatch", fake_dispatch)
    # 强制 SecretsService 走我们 mock path — 但本测试用 _setup_master_key fixture 已建老 key
    # 改 age < 90 通过改 last_rotated_at
    from datetime import datetime, timedelta, timezone

    from backend.repository.db import get_connection
    from backend.repository.encryption_keys_repo import EncryptionKeyRepository
    new = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    EncryptionKeyRepository()  # ensure import
    get_connection().execute(
        "UPDATE encryption_keys SET last_rotated_at = ? WHERE role = 'admin'",
        (new,),
    )

    await secrets_rotation_check_job()
    assert called == []
