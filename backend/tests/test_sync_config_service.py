"""P1.1: SyncConfigService 抽取测试。

测试意图 (Rule 9):
- upsert_config 的加密+校验+repo 逻辑应从 router 下沉到 service
- router 应只剩 HTTP 参数提取 / 响应构造
- service 应可独立测试 (不依赖 HTTP)

这些测试验证的是"分层职责"意图:
router 不做业务逻辑, service 不做 HTTP 处理。
"""
from __future__ import annotations


import pytest

from backend.config import config
from backend.repository import db
from backend.repository.sync_configs_repo import SyncConfigRepository


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    test_db = tmp_path / "sync_config.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.init_db()
    yield test_db
    db.close_db()


def _setup_master_key(master_key: str = "test_master_key_123") -> str:
    """初始化 master key (setup 流程), 返回 master_key。"""
    from backend.repository.encryption_keys_repo import EncryptionKeyRepository

    EncryptionKeyRepository().setup_default(master_key=master_key)
    return master_key


def test_sync_config_service_exists():
    """P1.1: SyncConfigService 应存在且可导入。"""
    from backend.services.sync_config_service import SyncConfigService

    assert callable(SyncConfigService)


def test_service_upsert_creates_config(temp_db):
    """P1.1: service.upsert 应创建/更新 sync config。

    修复前: api/sync.py 的 upsert_config handler 直接做加密+repo 操作
    修复后: service 提供 upsert_config 方法, router 只调用
    """
    from backend.services.sync_config_service import SyncConfigService

    _setup_master_key()

    svc = SyncConfigService()
    result = svc.upsert_config(
        webdav_url="https://dav.example.com",
        webdav_username="user",
        webdav_password="secret_pass",
        master_key="test_master_key_123",
        remote_path="/hotspot/config.json",
        auto_sync_enabled=False,
        auto_sync_interval_minutes=10080,
        sync_frequency="weekly",
    )

    assert result is not None
    # 验证 config 确实落库且密码已加密
    cfg = SyncConfigRepository().get_default()
    assert cfg is not None
    assert cfg.webdav_url == "https://dav.example.com"
    assert cfg.webdav_username == "user"
    # 密码应为密文 (非明文)
    assert cfg.webdav_password_encrypted is not None
    assert cfg.webdav_password_encrypted != "secret_pass"


def test_service_upsert_rejects_no_password_first_time(temp_db):
    """P1.1: 首次配置无密码 → 应拒绝 (409 语义)。

    service 应返回错误, 而非抛 HTTPException (HTTP 是 router 层职责)。
    """
    from backend.services.sync_config_service import SyncConfigService

    _setup_master_key()

    svc = SyncConfigService()
    # 未配置 + 无密码 → 应抛 ValueError (router 层转 409)
    with pytest.raises(ValueError):
        svc.upsert_config(
            webdav_url="https://dav.example.com",
            webdav_username="user",
            webdav_password="",
            master_key="test_master_key_123",
            remote_path="/hotspot/config.json",
        )


def test_service_delete_removes_config(temp_db):
    """P1.1: service.delete 应删除 config + 清空 states。"""
    from backend.services.sync_config_service import SyncConfigService

    _setup_master_key()

    svc = SyncConfigService()
    svc.upsert_config(
        webdav_url="https://dav.example.com",
        webdav_username="user",
        webdav_password="secret_pass",
        master_key="test_master_key_123",
        remote_path="/hotspot/config.json",
    )

    # 删除
    deleted = svc.delete_config()
    assert deleted is True

    # config 应为空
    assert SyncConfigRepository().get_default() is None


def test_service_set_auto_sync(temp_db):
    """P1.1: service.set_auto_sync 应只改 enabled。"""
    from backend.services.sync_config_service import SyncConfigService

    _setup_master_key()

    svc = SyncConfigService()
    svc.upsert_config(
        webdav_url="https://dav.example.com",
        webdav_username="user",
        webdav_password="secret_pass",
        master_key="test_master_key_123",
        remote_path="/hotspot/config.json",
        auto_sync_enabled=False,
    )

    # 开启自动同步
    svc.set_auto_sync(enabled=True)

    cfg = SyncConfigRepository().get_default()
    assert cfg is not None
    assert cfg.auto_sync_enabled is True