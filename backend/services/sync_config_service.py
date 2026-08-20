"""P1.1: Sync Config 业务逻辑 (从 api/sync.py 下沉)。

职责
----
- upsert_config: WebDAV 配置的加密 + 校验 + 落库
- delete_config: 删除配置 + 清空 states
- set_auto_sync: 切换自动同步
- get_default / has_config: 只读查询

设计
----
- 不 import HTTP 层 (FastAPI HTTPException)。错误通过 ValueError 抛出,
  router 层负责转 HTTP 状态码。
- 加密逻辑从 api/sync.py 的 _encrypt_webdav_password 迁移到此。

P1.1: 让 api/sync.py 的 handler 只剩 HTTP 参数提取 / 响应构造。
"""
from __future__ import annotations

import secrets as _secrets

from cryptography.fernet import Fernet as _F

from backend.crypto import DEFAULT_ITERATIONS, _derive_key, verify_master_key
from backend.repository.encryption_keys_repo import EncryptionKeyRepository
from backend.repository.sync_configs_repo import SyncConfigRepository
from backend.repository.sync_states_repo import SyncStateRepository


class SyncConfigService:
    """Sync 配置管理业务层。"""

    def __init__(self) -> None:
        self._cfg_repo = SyncConfigRepository()
        self._ek_repo = EncryptionKeyRepository()
        self._state_repo = SyncStateRepository()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _encrypt_password(self, password: str, master_key: str) -> tuple[bytes, bytes, int]:
        """用 master_key + 独立 salt 派生 fernet_key, Fernet 加密 password。

        salt 16 字节随机; iters = 600k (Q1 决策: 独立加密字段, 不复用 encryption_keys)。
        """
        salt = _secrets.token_bytes(16)
        iters = DEFAULT_ITERATIONS
        fernet_key = _derive_key(master_key, salt, iters)
        cipher = _F(fernet_key).encrypt(password.encode("utf-8"))
        return cipher, salt, iters

    def _verify_master_key(self, master_key: str) -> None:
        """验证 master_key; 未初始化或错误则抛 ValueError。"""
        ek = self._ek_repo.get_default()
        if ek is None:
            raise ValueError("主密钥未初始化; 请先调用 /api/secrets/setup")
        if not verify_master_key(master_key, ek.salt, ek.iterations, ek.verify_blob):
            raise ValueError("主密钥错误")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def upsert_config(
        self,
        *,
        webdav_url: str,
        webdav_username: str,
        webdav_password: str | None,
        master_key: str,
        remote_path: str = "/hotspot/config.json",
        auto_sync_enabled: bool = False,
        auto_sync_interval_minutes: int = 10080,
        sync_frequency: str = "weekly",
    ) -> dict:
        """upsert WebDAV 配置。

        - 验证 master_key (须先 setup)
        - 已配置 + webdav_password 留空 → 保留原密文 (不重新加密)
        - 已配置 + webdav_password 提供 → 重新派生 fernet_key 加密
        - 未配置 + webdav_password 留空 → 抛 ValueError (首次必须提供)
        """
        self._verify_master_key(master_key)

        existing = self._cfg_repo.get_default()
        new_password = (webdav_password or "").strip()

        if not new_password:
            if existing is None or existing.webdav_password_encrypted is None:
                raise ValueError(
                    "首次配置必须提供 WebDAV 应用密码; 已配置时留空 = 不修改"
                )
            # 已配置: 保留原密文/salt
            cipher, salt, iters = None, None, existing.webdav_password_iters
        else:
            cipher, salt, iters = self._encrypt_password(new_password, master_key)

        cfg = self._cfg_repo.upsert(
            webdav_url=webdav_url,
            webdav_username=webdav_username,
            webdav_password_encrypted=cipher,
            webdav_password_salt=salt,
            webdav_password_iters=iters,
            remote_path=remote_path,
            auto_sync_enabled=auto_sync_enabled,
            auto_sync_interval_minutes=auto_sync_interval_minutes,
            sync_frequency=sync_frequency,
        )
        return cfg.to_dict()

    def delete_config(self) -> bool:
        """删除 sync 配置 (并清空 sync_states / history)。"""
        cfg = self._cfg_repo.get_default()
        if cfg is None:
            raise ValueError("sync config 不存在")
        self._cfg_repo.delete(cfg.id)
        self._state_repo.clear(cfg.id)
        # 不删 history (审计)
        return True

    def set_auto_sync(self, *, enabled: bool) -> bool:
        """开启/关闭自动同步 (只改 enabled, 不改 webdav 凭据)。"""
        cfg = self._cfg_repo.get_default()
        if cfg is None:
            raise ValueError("请先调用 /api/sync/config 配置 WebDAV")
        self._cfg_repo.upsert(
            webdav_url=cfg.webdav_url,
            webdav_username=cfg.webdav_username,
            auto_sync_enabled=enabled,
            auto_sync_interval_minutes=cfg.auto_sync_interval_minutes,
            remote_path=cfg.remote_path,
            device_id=cfg.device_id,
        )
        return True

    def has_config(self) -> bool:
        return self._cfg_repo.get_default() is not None


__all__ = ["SyncConfigService"]