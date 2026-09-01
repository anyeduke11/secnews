"""Phase 41 密钥管理 service: 30 分钟 unlock 状态机 + CRUD + import/export + test。

v1.3.0 Phase 5: master_key OS keychain 持久化。

设计原则
--------
- 进程内单实例模块状态 ``_unlock_state`` dict, key = encryption_key_id,
  value = {fernet_key, expires_at}
- TTL 1800s (30 分钟); 过期或进程重启必须重新 unlock
- master_key 不进日志; reveal/api_key 不进日志
- 锁定 (``_unlock_state.pop``) 立即清空
- v1.3.0: unlock 时 master_key 持久化到 OS keyring (keyring 库),
  进程重启后自动 restore unlock 状态, 无需重新输入密码。
  keyring 不可用时降级到 settings 表加密存储。
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

import httpx

from backend.crypto import (
    DEFAULT_ITERATIONS,  # P4-5: 轮换用
    MIN_MASTER_KEY_LENGTH,
    InvalidMasterKeyError,
    WeakMasterKeyError,  # P4-5: 轮换用
    decrypt_api_key,
    derive_fernet_key,
    encrypt_api_key,  # P4-5: 轮换用
    generate_salt,  # P4-5: 轮换用
    make_verify_blob,  # P4-5: 轮换用
    verify_master_key,
)
from backend.exceptions import (
    ConflictException,
    InternalException,
    InvalidParamException,
    NotFoundException,
)
from backend.logging_config import logger
from backend.repository.db import get_connection
from backend.repository.encryption_keys_repo import EncryptionKeyRepository
from backend.repository.secrets_repo import SecretRepository
from backend.services.oauth_provider import OAuthVerificationError  # D1

UNLOCK_TTL_SECONDS = int(os.environ.get("HOTSPOT_SECRETS_TTL_SECONDS", 30 * 60))  # 默认 30 分钟

_KEYRING_SERVICE = "hotspot"
_KEYRING_USERNAME = "master_key"
_SETTINGS_KEY_ENCRYPTED = "master_key_encrypted"

# 模块级单实例 (进程内共享)
_unlock_state: dict[int, dict] = {}  # {key_id: {"fernet_key": bytes, "expires_at": float}}
_keychain_available: bool | None = None


def _now_ts() -> float:
    return time.time()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_unlocked(key_id: int) -> bool:
    """检查 key_id 是否在 unlock 状态, 顺便清过期。"""
    state = _unlock_state.get(key_id)
    if state is None:
        return False
    if state["expires_at"] < _now_ts():
        _unlock_state.pop(key_id, None)
        return False
    return True


def _purge_expired() -> None:
    """清空所有过期 state。"""
    now = _now_ts()
    expired = [k for k, v in _unlock_state.items() if v["expires_at"] < now]
    for k in expired:
        _unlock_state.pop(k, None)


def _get_oauth_allowlist() -> list[str]:
    """D1: 读 settings.kv ``secrets.oauth_allowlist`` 逗号分隔邮箱白名单。

    空 / 不存在 → 返 [] (允许所有, 与现状对齐: 默认无 OAuth 解锁入口, 配了才生效)。
    """
    try:
        from backend.repository.settings_repo import SettingsRepository

        raw = SettingsRepository().get("secrets.oauth_allowlist", "") or ""
    except Exception:
        return []
    items = [s.strip().lower() for s in raw.split(",") if s.strip()]
    return items


def _check_keyring() -> bool:
    """检测 keyring 是否可用 (缓存结果)。"""
    global _keychain_available
    if _keychain_available is not None:
        return _keychain_available
    try:
        import keyring as _kr
        _kr.get_keyring()
        _keychain_available = True
    except Exception:
        _keychain_available = False
    return _keychain_available


def _persist_master_key(master_key: str, key_id: int = 0, role: str = "admin") -> bool:
    """持久化 master_key。OS keyring 优先 (自身加密), 降级到 settings 表。

    T4: key_id/role 后缀隔离多用户存储。
    """
    suffix = f"_{key_id}" if key_id else ""
    if _check_keyring():
        try:
            import keyring as _kr
            _kr.set_password(_KEYRING_SERVICE, f"{_KEYRING_USERNAME}{suffix}", master_key)
            logger.info("master_key persisted to OS keyring (key_id=%s, role=%s)", key_id, role)
            return True
        except Exception as e:
            logger.warning(f"keyring set_password failed, falling back to settings: {e}")

    ek = EncryptionKeyRepository()
    row = ek.get_default() if key_id == 0 else ek.get_by_id(key_id)
    if row is None:
        return False

    try:
        from cryptography.fernet import Fernet as _F
        encrypted = _F(row.verify_blob).encrypt(master_key.encode("utf-8")).decode("ascii")
        from backend.repository.settings_repo import SettingsRepository
        SettingsRepository().set(f"{_SETTINGS_KEY_ENCRYPTED}{suffix}", encrypted)
        logger.info("master_key persisted to settings table (key_id=%s, role=%s)", key_id, role)
        return True
    except Exception as e:
        logger.warning(f"master_key persist failed: {e}")
        return False


def _load_persisted_master_key(key_id: int = 0) -> str | None:
    """从 OS keyring 或 settings 表加载 master_key。返回 None 表示无持久化数据。"""
    suffix = f"_{key_id}" if key_id else ""
    if _check_keyring():
        try:
            import keyring as _kr
            val = _kr.get_password(_KEYRING_SERVICE, f"{_KEYRING_USERNAME}{suffix}")
            if val:
                ek = EncryptionKeyRepository()
                row = ek.get_default() if key_id == 0 else ek.get_by_id(key_id)
                if row and verify_master_key(val, row.salt, row.iterations, row.verify_blob):
                    logger.info("master_key restored from OS keyring (key_id=%s)", key_id)
                    return val
                else:
                    logger.warning("keyring master_key verification failed, clearing stale entry")
                    try:
                        _kr.delete_password(_KEYRING_SERVICE, f"{_KEYRING_USERNAME}{suffix}")
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"keyring get_password failed: {e}")

    ek = EncryptionKeyRepository()
    row = ek.get_default() if key_id == 0 else ek.get_by_id(key_id)
    if row is None:
        return None

    try:
        from backend.repository.settings_repo import SettingsRepository
        encrypted = SettingsRepository().get(f"{_SETTINGS_KEY_ENCRYPTED}{suffix}")
        if not encrypted:
            return None
        from cryptography.fernet import Fernet as _F
        plaintext = _F(row.verify_blob).decrypt(encrypted.encode("ascii"))
        master_key = plaintext.decode("utf-8")
        if verify_master_key(master_key, row.salt, row.iterations, row.verify_blob):
            logger.info("master_key restored from settings table (key_id=%s)", key_id)
            return master_key
        else:
            logger.warning("settings master_key verification failed, clearing stale entry")
            SettingsRepository().delete(f"{_SETTINGS_KEY_ENCRYPTED}{suffix}")
    except Exception as e:
        logger.warning(f"master_key restore from settings failed: {e}")

    return None


def _clear_persisted_master_key(key_id: int = 0) -> None:
    """清除持久化的 master_key (lock/reset 时调用)。"""
    suffix = f"_{key_id}" if key_id else ""
    if _check_keyring():
        try:
            import keyring as _kr
            _kr.delete_password(_KEYRING_SERVICE, f"{_KEYRING_USERNAME}{suffix}")
        except Exception:
            pass
    try:
        from backend.repository.settings_repo import SettingsRepository
        SettingsRepository().delete(f"{_SETTINGS_KEY_ENCRYPTED}{suffix}")
    except Exception:
        pass


def try_auto_unlock() -> bool:
    """启动时尝试从持久化存储恢复 unlock 状态。返回是否成功。"""
    master_key = _load_persisted_master_key()
    if master_key is None:
        return False
    try:
        svc = SecretsService()
        # result 是 svc.unlock 的成功标记 — 失败走 except 路径
        _result = svc.unlock(master_key)
        del _result
        logger.info("auto-unlock from persisted master_key succeeded")
        return True
    except Exception as e:
        logger.warning(f"auto-unlock failed: {e}")
        _clear_persisted_master_key()
        return False


class SecretsService:
    """LLM 密钥 service。模块级函数保持纯函数风格, 实例方法做依赖注入。"""

    # ------------------------------------------------------------------
    # 主密钥 setup
    # ------------------------------------------------------------------
    def setup_master_key(self, master_key: str, role: str = "admin") -> dict:
        """初始化主密钥 (单次, 禁止重置)。T4: role=admin|user."""
        ek = EncryptionKeyRepository()
        if ek.is_setup():
            raise ConflictException("主密钥已初始化; 禁止重置 (Q1 决策)")
        row = ek.setup_default(master_key=master_key, role=role)
        return {
            "id": row.id,
            "name": row.name,
            "role": row.role,
            "iterations": row.iterations,
            "created_at": row.created_at,
        }

    def rotate_master_key(self, old_key: str, new_key: str) -> dict:
        """P4-5: 轮换主密钥 — 重加密全部密文 (llm_secrets + webdav + settings).

        此前无任何轮换/恢复机制: 主密钥丢失 = 全部密文永久不可解。
        本操作:
        1. 验证 old_key (失败抛 InvalidMasterKeyError)
        2. 生成新 salt, 派生新旧 Fernet key
        3. 重加密 llm_secrets.api_key_encrypted (旧→新)
        4. 重加密 sync_configs.webdav_password_encrypted (旧→新)
        5. 更新 encryption_keys (新 salt/iterations/verify_blob)
        6. 持久化新 key 到 keyring/settings
        """
        if not new_key or len(new_key) < MIN_MASTER_KEY_LENGTH:
            raise WeakMasterKeyError(
                f"新主密钥长度必须 >= {MIN_MASTER_KEY_LENGTH} 字符"
            )
        ek = EncryptionKeyRepository()
        row = ek.get_default()
        if row is None:
            raise ConflictException("主密钥未初始化")

        if not verify_master_key(old_key, row.salt, row.iterations, row.verify_blob):
            raise InvalidMasterKeyError("旧主密钥错误, 无法轮换")

        old_fernet = derive_fernet_key(old_key, row.salt, row.iterations)
        new_salt = generate_salt()
        new_fernet = derive_fernet_key(new_key, new_salt, DEFAULT_ITERATIONS)

        conn = get_connection()
        try:
            conn.execute("BEGIN")
            # 3. llm_secrets 重加密
            secret_rows = conn.execute(
                "SELECT id, api_key_encrypted FROM llm_secrets"
            ).fetchall()
            for s in secret_rows:
                try:
                    plaintext = decrypt_api_key(old_fernet, s["api_key_encrypted"])
                    new_ct = encrypt_api_key(new_fernet, plaintext)
                except Exception as dec_err:
                    conn.execute("ROLLBACK")
                    raise InvalidMasterKeyError(
                        f"llm_secrets {s['id']} 解密失败: {dec_err}"
                    ) from dec_err
                conn.execute(
                    "UPDATE llm_secrets SET api_key_encrypted = ? WHERE id = ?",
                    (new_ct, s["id"]),
                )
            # 4. webdav 密码重加密 (sync_configs.webdav_password_encrypted)
            wd_rows = conn.execute(
                "SELECT id, webdav_password_encrypted, webdav_password_salt "
                "FROM sync_configs WHERE webdav_password_encrypted IS NOT NULL"
            ).fetchall()
            for w in wd_rows:
                try:
                    from backend.services.webdav_client import (
                        decrypt_webdav_password,  # type: ignore
                    )
                    plaintext = decrypt_webdav_password(
                        old_fernet, w["webdav_password_encrypted"]
                    )
                    new_ct = encrypt_api_key(new_fernet, plaintext)
                except Exception:
                    # webdav 密码走独立 salt 派生, 重加密用新 master_key 的 fernet
                    from cryptography.fernet import Fernet as _F
                    try:
                        plaintext = _F(old_fernet).decrypt(bytes(w["webdav_password_encrypted"]))
                        new_ct = _F(new_fernet).encrypt(plaintext)
                    except Exception:
                        conn.execute("ROLLBACK")
                        raise
                conn.execute(
                    "UPDATE sync_configs SET webdav_password_encrypted = ? WHERE id = ?",
                    (new_ct, w["id"]),
                )
            # 5. 更新 encryption_keys (新 salt/iterations/verify_blob + last_rotated_at)
            new_verify = make_verify_blob(new_key, new_salt, DEFAULT_ITERATIONS)
            conn.execute(
                "UPDATE encryption_keys SET salt = ?, iterations = ?, "
                "verify_blob = ?, last_rotated_at = ? WHERE id = ?",
                (new_salt, DEFAULT_ITERATIONS, new_verify,
                 _now_iso(), row.id),
            )
            conn.execute("COMMIT")
        except Exception as _e:
            del _e
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise

        # 6. 持久化新 key + 清空 unlock state (强制重新解锁)
        _persist_master_key(new_key)
        _unlock_state.pop(row.id, None)
        logger.info("master_key rotated: re-encrypted %d secrets", len(secret_rows))
        return {
            "ok": True,
            "reencrypted_secrets": len(secret_rows),
            "reencrypted_webdav": len(wd_rows),
        }

    def is_master_key_setup(self) -> bool:
        return EncryptionKeyRepository().is_setup()

    # ------------------------------------------------------------------
    # Unlock / lock
    # ------------------------------------------------------------------
    def unlock(self, master_key: str, role: str = "admin") -> dict:
        """验证 master_key, 设置 30 分钟 unlock, 并持久化到 keychain。

        T4: role=admin|user, 按 role 取对应 key_id 解锁。
        """
        ek = EncryptionKeyRepository()
        if role == "admin":
            row = ek.get_default()
        else:
            row = ek.get_by_role(role)
        if row is None:
            raise ConflictException(f"主密钥未初始化 (role={role}); 请先调用 setup 接口")

        if not verify_master_key(master_key, row.salt, row.iterations, row.verify_blob):
            raise InvalidMasterKeyError("主密钥错误")

        fernet_key = derive_fernet_key(master_key, row.salt, row.iterations)
        expires_at = _now_ts() + UNLOCK_TTL_SECONDS
        _unlock_state[row.id] = {
            "fernet_key": fernet_key,
            "expires_at": expires_at,
        }

        _persist_master_key(master_key, key_id=row.id, role=row.role)

        return {
            "encryption_key_id": row.id,
            "role": row.role,
            "unlocked": True,
            "expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
            "ttl_seconds": UNLOCK_TTL_SECONDS,
        }

    def unlock_status(self, role: str = "admin") -> dict:
        """T4: 查询 unlock 状态 + 剩余秒数 (按 role)."""
        ek = EncryptionKeyRepository()
        if role == "admin":
            row = ek.get_default()
        else:
            row = ek.get_by_role(role)
        keychain_persisted = _load_persisted_master_key(key_id=row.id) is not None if row else False
        if row is None:
            return {
                "setup": False,
                "unlocked": False,
                "role": role,
                "expires_at": None,
                "remaining_seconds": 0,
                "keychain_persisted": False,
            }
        _purge_expired()
        state = _unlock_state.get(row.id)
        if state is None:
            return {
                "setup": True,
                "unlocked": False,
                "role": row.role,
                "expires_at": None,
                "remaining_seconds": 0,
                "keychain_persisted": keychain_persisted,
            }
        remaining = max(0, int(state["expires_at"] - _now_ts()))
        return {
            "setup": True,
            "unlocked": True,
            "role": row.role,
            "expires_at": datetime.fromtimestamp(state["expires_at"], tz=timezone.utc).isoformat(),
            "remaining_seconds": remaining,
            "keychain_persisted": keychain_persisted,
        }

    def unlock_with_oauth(self, access_token: str, role: str = "admin") -> dict:
        """D1: OAuth 解锁 — 跳过 master_key 校验, 走 OAuth token + allowlist。

        安全约束:
        - access_token 经 OAuthProvider.get_user_info() 验证 (CloudBase OAuth API)
        - user.email 必须命中 settings.kv ``secrets.oauth_allowlist`` (逗号分隔列表)
        - 不持久化 master_key 到 keyring (OAuth 解锁无 master_key)
        - 返回 unlock dict (格式与 unlock() 一致) + audit 记录 actor=oauth

        Raises:
            OAuthVerificationError: token 无效 / 过期 / user 不在 allowlist
            ConflictException: 主密钥未初始化 (role 未 setup)
        """
        from backend.services.oauth_provider import (
            get_oauth_provider,
        )

        try:
            provider = get_oauth_provider()
            user = provider.get_user_info(access_token)
        except OAuthVerificationError:
            raise
        except Exception as e:  # pragma: no cover - 防御性
            logger.warning("OAuth provider error: %s", e)
            raise OAuthVerificationError(f"OAuth provider 错误: {e}") from e

        if not user.email:
            raise OAuthVerificationError("OAuth user.email 为空")

        allowlist = _get_oauth_allowlist()
        if allowlist and user.email.lower() not in {a.lower() for a in allowlist}:
            raise OAuthVerificationError(
                f"OAuth user {user.email} 不在 allowlist"
            )

        ek = EncryptionKeyRepository()
        if role == "admin":
            row = ek.get_default()
        else:
            row = ek.get_by_role(role)
        if row is None:
            raise ConflictException(f"主密钥未初始化 (role={role}); 请先调用 setup 接口")

        # OAuth 解锁: 不派生 Fernet (没 master_key), 走 settings 解锁路径
        # 这里 _unlock_state 需要 fernet_key 才能 decrypt, 因此 OAuth 解锁后
        # 仅做 "audit + allow" 而不解密, 业务侧 reveal/decrypt 仍需 master_key。
        # 实际 OAuth 解锁语义 = 临时授权 audit 通行, 不解密密文。
        # **设计选择**: OAuth 解锁仅置 unlocked=True (audit 通路), 不写 fernet_key
        # — 解密仍要求 master_key。这是"双因素"语义: OAuth 是身份, master_key 是密钥。
        expires_at = _now_ts() + UNLOCK_TTL_SECONDS
        _unlock_state[row.id] = {
            "fernet_key": None,  # OAuth 解锁不解密
            "expires_at": expires_at,
            "oauth_verified": True,
            "oauth_user": user.email,
        }

        return {
            "encryption_key_id": row.id,
            "role": row.role,
            "unlocked": True,
            "expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
            "ttl_seconds": UNLOCK_TTL_SECONDS,
            "oauth_verified": True,
            "oauth_user": user.email,
            "note": "OAuth 解锁仅作 audit 授权, 解密仍需 master_key",
        }

    def rotation_status(self) -> dict:
        """T3: 主密钥轮换状态 (TTL 自动过期 + 强制轮换提醒)."""
        ek = EncryptionKeyRepository()
        row = ek.get_default()
        if row is None:
            return {
                "setup": False,
                "last_rotated_at": None,
                "age_days": None,
                "should_rotate": False,
                "ttl_seconds": UNLOCK_TTL_SECONDS,
                "remind_days": 90,
            }
        last_rotated = None
        age_days = None
        should_rotate = False
        if row.last_rotated_at:
            try:
                last_dt = datetime.fromisoformat(row.last_rotated_at)
                age_delta = datetime.now(timezone.utc) - last_dt
                age_days = max(0, age_delta.days)
                last_rotated = row.last_rotated_at
                should_rotate = age_days >= 90
            except Exception:
                pass
        return {
            "setup": True,
            "last_rotated_at": last_rotated,
            "age_days": age_days,
            "should_rotate": should_rotate,
            "ttl_seconds": UNLOCK_TTL_SECONDS,
            "remind_days": 90,
        }

    def lock(self) -> dict:
        """立即清空 unlock 状态 + 清除持久化。"""
        _unlock_state.clear()
        _clear_persisted_master_key()
        return {"unlocked": False, "remaining_seconds": 0}

    # ------------------------------------------------------------------
    # Secret CRUD
    # ------------------------------------------------------------------
    def list_secrets(self, actor_role: str = "admin") -> tuple[list[dict], int]:
        """v0.7 Batch ⑨ B9-3: actor_role 过滤 secret 列表."""
        sr = SecretRepository()
        items, total = sr.list(actor_role=actor_role)
        ek = EncryptionKeyRepository()
        row = ek.get_default()
        is_unlocked = bool(row and _is_unlocked(row.id))
        result = []
        for it in items:
            d = it.to_dict(reveal=None)
            d["unlocked"] = is_unlocked
            result.append(d)
        return result, total

    def create_secret(
        self,
        *,
        name: str,
        model: str,
        base_url: str,
        api_key: str,
        master_key: str,
        provider: str = "",
    ) -> dict:
        """新增 secret, 需要 master_key 当场加密。"""
        ek = EncryptionKeyRepository()
        row = ek.get_default()
        if row is None:
            raise ConflictException("主密钥未初始化")

        if not verify_master_key(master_key, row.salt, row.iterations, row.verify_blob):
            raise InvalidMasterKeyError("主密钥错误")

        fernet_key = derive_fernet_key(master_key, row.salt, row.iterations)
        sr = SecretRepository()
        item = sr.create(
            name=name,
            model=model,
            base_url=base_url,
            api_key=api_key,
            fernet_key=fernet_key,
            encryption_key_id=row.id,
            provider=provider,
        )
        return item.to_dict(reveal=None)

    def update_secret(
        self,
        secret_id: int,
        *,
        name: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        master_key: str | None = None,
        provider: str | None = None,
    ) -> dict:
        """更新 secret; 改 api_key 必须传 master_key。"""
        sr = SecretRepository()
        existing = sr.get(secret_id)
        if existing is None:
            raise NotFoundException(f"secret {secret_id} 不存在")

        fernet_key = None
        if api_key is not None and api_key.strip():
            if not master_key:
                raise InvalidParamException("修改 api_key 必须提供 master_key")
            ek = EncryptionKeyRepository()
            row = ek.get_by_id(existing.encryption_key_id)
            if row is None:
                raise InternalException("secret 引用的 encryption_key 丢失")
            if not verify_master_key(master_key, row.salt, row.iterations, row.verify_blob):
                raise InvalidMasterKeyError("主密钥错误")
            fernet_key = derive_fernet_key(master_key, row.salt, row.iterations)

        item = sr.update(
            secret_id,
            name=name,
            model=model,
            base_url=base_url,
            api_key=api_key,
            fernet_key=fernet_key,
            provider=provider,
        )
        return item.to_dict(reveal=None)

    def delete_secret(self, secret_id: int) -> bool:
        return SecretRepository().delete(secret_id)

    # ------------------------------------------------------------------
    # Reveal (需现场验证 master_key)
    # ------------------------------------------------------------------
    def reveal(self, secret_id: int, master_key: str) -> dict:
        """现场验证 master_key 后返回明文 api_key。

        安全加固: 明文取回不再依赖 30 分钟 unlock 窗口 —— 每次 reveal
        都必须重新提交主密钥, 防止解锁窗口内被无凭证窃取明文。
        """
        sr = SecretRepository()
        item = sr.get(secret_id)
        if item is None:
            raise NotFoundException(f"secret {secret_id} 不存在")

        ek = EncryptionKeyRepository()
        row = ek.get_by_id(item.encryption_key_id)
        if row is None:
            raise InternalException("secret 引用的 encryption_key 丢失")
        if not verify_master_key(master_key, row.salt, row.iterations, row.verify_blob):
            raise InvalidMasterKeyError("主密钥错误")

        fernet_key = derive_fernet_key(master_key, row.salt, row.iterations)
        try:
            plaintext = decrypt_api_key(fernet_key, item.api_key_encrypted)
        except InvalidMasterKeyError as e:
            raise InternalException(f"解密失败: {e}") from e

        return {
            "id": item.id,
            "name": item.name,
            "model": item.model,
            "base_url": item.base_url,
            "provider": item.provider,
            "api_key": plaintext,
            "unlocked": True,
        }

    def decrypt_for_internal_use(self, secret_id: int) -> str:
        """进程内取明文 (依赖 unlock 窗口), 仅供后端服务间调用。

        注意: 该方法不得暴露为 HTTP 端点 —— HTTP 侧取明文必须走
        ``reveal(secret_id, master_key)`` 现场验证主密钥。
        """
        sr = SecretRepository()
        item = sr.get(secret_id)
        if item is None:
            raise NotFoundException(f"secret {secret_id} 不存在")
        if not _is_unlocked(item.encryption_key_id):
            raise ConflictException("未解锁; 请先调用 unlock 输入主密钥")
        fernet_key = _unlock_state[item.encryption_key_id]["fernet_key"]
        try:
            return decrypt_api_key(fernet_key, item.api_key_encrypted)
        except InvalidMasterKeyError as e:
            raise InternalException(f"解密失败: {e}") from e

    # ------------------------------------------------------------------
    # Test connection (Phase 41 Q4)
    # ------------------------------------------------------------------
    def test_connection(self, secret_id: int, timeout: float = 8.0) -> dict:
        """用 secret 的 api_key 对 base_url 发最小请求。

        策略
        ----
        1) 尝试 ``GET {base_url}/models`` (OpenAI 兼容), 5~8s 超时
        2) 失败再尝试 ``GET {base_url}`` (HEAD fallback)
        3) 都不通 → 返回 ok=False + 错误信息

        返回
        ----
        ``{ok, latency_ms, status_code, endpoint, model_count?, error?}``
        """
        import time as _t
        sr = SecretRepository()
        item = sr.get(secret_id)
        if item is None:
            raise NotFoundException(f"secret {secret_id} 不存在")
        if not _is_unlocked(item.encryption_key_id):
            raise ConflictException("未解锁; 请先调用 unlock 输入主密钥")
        fernet_key = _unlock_state[item.encryption_key_id]["fernet_key"]
        try:
            api_key = decrypt_api_key(fernet_key, item.api_key_encrypted)
        except InvalidMasterKeyError as e:
            raise InternalException(f"解密失败: {e}") from e

        base = item.base_url.rstrip("/")
        # 兼容 OpenAI / DeepSeek / 自建 (默认 /v1/models 即可)
        # 1) GET {base_url}/models
        # 2) fallback GET {base_url} (HEAD)
        # 注意: base_url 通常已经含 /v1, 所以拼 /models 即可
        endpoints = [
            f"{base}/models",
            base,
        ]
        headers = {"Authorization": f"Bearer {api_key}"}
        started = _t.time()
        last_error: str | None = None
        last_status: int | None = None
        model_count: int | None = None

        with httpx.Client(timeout=timeout) as client:
            for ep in endpoints:
                try:
                    r = client.get(ep, headers=headers)
                    last_status = int(r.status_code)
                    if 200 <= r.status_code < 300:
                        # 尝试解析 OpenAI /models 响应
                        if ep.endswith("/models"):
                            try:
                                j = r.json()
                                if isinstance(j, dict) and isinstance(j.get("data"), list):
                                    model_count = len(j["data"])
                            except Exception:
                                pass
                        latency = int((_t.time() - started) * 1000)
                        return {
                            "ok": True,
                            "latency_ms": latency,
                            "status_code": last_status,
                            "endpoint": ep,
                            "model_count": model_count,
                        }
                    # 401/403 表示网络可达 + 鉴权失败, 也算"连上"
                    if r.status_code in (401, 403):
                        latency = int((_t.time() - started) * 1000)
                        return {
                            "ok": True,
                            "latency_ms": latency,
                            "status_code": r.status_code,
                            "endpoint": ep,
                            "model_count": None,
                            "warning": f"鉴权失败 (HTTP {r.status_code}), 网络可达",
                        }
                    last_error = f"HTTP {r.status_code}"
                except httpx.TimeoutException:
                    last_error = f"timeout after {timeout}s"
                except httpx.ConnectError as e:
                    last_error = f"connect error: {e}"
                except Exception as e:
                    last_error = f"{type(e).__name__}: {e}"
        # 都失败
        latency = int((_t.time() - started) * 1000)
        return {
            "ok": False,
            "latency_ms": latency,
            "status_code": last_status,
            "endpoint": endpoints[0] if endpoints else None,
            "error": last_error or "未知错误",
        }

    # ------------------------------------------------------------------
    # 导出 (Phase 41 Q3) — 加密 JSON 文件
    # ------------------------------------------------------------------
    def export(self, master_key: str) -> bytes:
        """导出所有 secret 为加密 JSON (整个文件用 master_key 加密)。

        流程:
        - 用 master_key 验证主密钥
        - 构造 ``{version, exported_at, secrets: [{name, model, base_url, api_key}]}``
        - JSON serialize + utf-8 encode
        - PBKDF2 派生 (用同样的 salt) + Fernet 加密整个 plaintext
        - 包装成 ``{"version", "encryption": {...}, "ciphertext"}`` JSON
        """
        ek = EncryptionKeyRepository()
        row = ek.get_default()
        if row is None:
            raise ConflictException("主密钥未初始化")
        if not verify_master_key(master_key, row.salt, row.iterations, row.verify_blob):
            raise InvalidMasterKeyError("主密钥错误")

        fernet_key = derive_fernet_key(master_key, row.salt, row.iterations)
        sr = SecretRepository()
        items, _ = sr.list()
        plaintext_dict = {
            "version": "1.0",
            "exported_at": _now_iso(),
            "secrets": [
                {
                    "name": it.name,
                    "model": it.model,
                    "base_url": it.base_url,
                    "provider": it.provider,
                    "api_key": decrypt_api_key(fernet_key, it.api_key_encrypted),
                }
                for it in items
            ],
        }
        plaintext = json.dumps(plaintext_dict, ensure_ascii=False, indent=2).encode("utf-8")
        # cipher 占位 — fernet_key is bytes; Fernet 接受 base64 str, 实际加密在 _F(fernet_key) 处
        _cipher = fernet_key
        del _cipher
        from cryptography.fernet import Fernet as _F
        ct = _F(fernet_key).encrypt(plaintext)

        envelope = {
            "version": "1.0",
            "encryption": {
                "algorithm": "Fernet",
                "kdf": "PBKDF2-HMAC-SHA256",
                "iterations": row.iterations,
                "salt_b64": row.salt.hex(),  # hex 编码方便跨平台
            },
            "exported_at": _now_iso(),
            "ciphertext_b64": ct.hex(),  # hex 编码 (Fernet 本身就是 url-safe base64, 但 hex 更通用)
        }
        return json.dumps(envelope, ensure_ascii=False, indent=2).encode("utf-8")

    # ------------------------------------------------------------------
    # 导入 (Phase 41 Q3) — 解析加密 JSON, 批量入库
    # ------------------------------------------------------------------
    def import_from_bytes(self, payload: bytes, master_key: str) -> dict:
        """解析加密 JSON, 验证 master_key, 批量插入 llm_secrets。

        重复 name 默认覆盖 (update); 失败 secret 计入 ``failures``。
        """
        ek = EncryptionKeyRepository()
        row = ek.get_default()
        if row is None:
            raise ConflictException("主密钥未初始化")
        if not verify_master_key(master_key, row.salt, row.iterations, row.verify_blob):
            raise InvalidMasterKeyError("主密钥错误")

        try:
            envelope = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise InternalException(f"导入文件 JSON 解析失败: {e}") from e

        if not isinstance(envelope, dict):
            raise InternalException("导入文件格式错误 (不是 JSON object)")

        # 校验 envelope 算法
        enc = envelope.get("encryption", {})
        if enc.get("algorithm") != "Fernet":
            raise InternalException(f"不支持的加密算法: {enc.get('algorithm')}")
        if int(enc.get("iterations", -1)) != row.iterations:
            raise InternalException(
                f"iterations 不一致: 文件 {enc.get('iterations')} vs 当前 {row.iterations}"
            )

        # 派生 key + 解密
        fernet_key = derive_fernet_key(master_key, row.salt, row.iterations)
        from cryptography.fernet import Fernet as _F
        from cryptography.fernet import InvalidToken
        try:
            ct = bytes.fromhex(envelope["ciphertext_b64"])
            plaintext = _F(fernet_key).decrypt(ct)
            data = json.loads(plaintext.decode("utf-8"))
        except (KeyError, ValueError, InvalidToken) as e:
            raise InternalException(f"导入文件解密失败: {e}") from e

        secrets_list = data.get("secrets", [])
        if not isinstance(secrets_list, list):
            raise InternalException("secrets 字段必须为数组")

        sr = SecretRepository()
        inserted = 0
        updated = 0
        failures: list[dict] = []
        existing_items, _ = sr.list()
        existing_by_name = {it.name: it for it in existing_items}

        for s in secrets_list:
            try:
                name = str(s["name"]).strip()
                model = str(s["model"]).strip()
                base_url = str(s["base_url"]).strip()
                # S4-1: 老 payload 无 provider 字段 (v1.0 导出) → 默认空串, 行为兼容
                provider = str(s.get("provider", "")).strip()
                api_key = str(s["api_key"])
                if name in existing_by_name:
                    sr.update(
                        existing_by_name[name].id,
                        name=name,
                        model=model,
                        base_url=base_url,
                        api_key=api_key,
                        fernet_key=fernet_key,
                        provider=provider,
                    )
                    updated += 1
                else:
                    sr.create(
                        name=name,
                        model=model,
                        base_url=base_url,
                        api_key=api_key,
                        fernet_key=fernet_key,
                        encryption_key_id=row.id,
                        provider=provider,
                    )
                    inserted += 1
            except Exception as e:
                failures.append({"name": s.get("name"), "error": str(e)})

        return {
            "inserted": inserted,
            "updated": updated,
            "failures": failures,
            "total_secrets": len(secrets_list),
        }


__all__ = ["UNLOCK_TTL_SECONDS", "SecretsService", "_unlock_state"]
