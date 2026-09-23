"""P1.2: sync_service.py 拆分测试 (FernetKeySyncMixin 抽取)。

测试意图 (Rule 9):
- SyncService 应继承 FernetKeySyncMixin (拆分成功)
- fernet-key 同步方法应存在于 SyncService 实例 (通过 mixin)
- 主类仍保留 master_key 同步方法
- 常量集中在 sync_service_constants, 不重复定义
"""
from __future__ import annotations


def test_sync_service_inherits_mixin():
    """P1.2: SyncService 应为 FernetKeySyncMixin 子类。"""
    from backend.services.sync_fernet_mixin import FernetKeySyncMixin
    from backend.services.sync_service import SyncService

    assert issubclass(SyncService, FernetKeySyncMixin)


def test_fernet_methods_available_on_service():
    """P1.2: fernet-key 同步方法应由 mixin 提供给 SyncService。"""
    from backend.services.sync_service import SyncService

    svc = SyncService()
    # mixin 提供的方法
    assert hasattr(svc, "bidirectional_with_fernet_key")
    assert hasattr(svc, "_push_with_fernet_key")
    assert hasattr(svc, "_pull_with_fernet_key")
    assert hasattr(svc, "decrypt_bundle_with_fernet_key")


def test_master_key_methods_remain_on_service():
    """P1.2: 主类的 master_key 同步方法应保留。"""
    from backend.services.sync_service import SyncService

    svc = SyncService()
    assert hasattr(svc, "push")
    assert hasattr(svc, "pull")
    assert hasattr(svc, "bidirectional")
    assert hasattr(svc, "build_bundle")
    assert hasattr(svc, "apply_bundle")
    assert hasattr(svc, "status")
    assert hasattr(svc, "history")


def test_constants_centralized():
    """P1.2: 常量应从 sync_service_constants 引用, 不重复定义。

    mixin 与主类共享 BUNDLE_VERSION 等, 避免两份维护。
    """
    from backend.services.sync_service_constants import (
        BUNDLE_VERSION,
        SECRET_MERGE_FIELDS,
        SETTINGS_SYNC_PREFIXES,
        settings_sync_allowed,
    )

    assert BUNDLE_VERSION == "1.0"
    assert isinstance(SECRET_MERGE_FIELDS, tuple)
    # P3 Task 16: settings 跨端同步白名单化 (blocklist 反转), 防未来敏感键误同步
    assert SETTINGS_SYNC_PREFIXES == ("collection.", "llm.", "interest.", "quality.")
    assert settings_sync_allowed("llm.model")
    assert not settings_sync_allowed("scheduler.last_run")
    assert not settings_sync_allowed("webhook.secret")


def test_mixin_imports_without_circular():
    """P1.2: mixin 与主类无循环导入。"""
    from backend.services import sync_fernet_mixin, sync_service  # noqa: F401

    assert True