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
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

from backend.crypto import (
    DEFAULT_ITERATIONS,
    InvalidMasterKeyError,
    derive_fernet_key,
    decrypt_api_key,
    verify_master_key,
)
from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.encryption_keys_repo import EncryptionKeyRepository
from backend.repository.secrets_repo import SecretRepository


UNLOCK_TTL_SECONDS = 30 * 60  # 30 分钟

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


def _persist_master_key(master_key: str) -> bool:
    """持久化 master_key。OS keyring 优先 (自身加密), 降级到 settings 表。

    OS keyring 模式: keyring 自身提供加密, 直接存明文 master_key。
    settings 表模式: 用 verify_blob 作为 Fernet key 加密 master_key 后存储。
    """
    if _check_keyring():
        try:
            import keyring as _kr
            _kr.set_password(_KEYRING_SERVICE, _KEYRING_USERNAME, master_key)
            logger.info("master_key persisted to OS keyring")
            return True
        except Exception as e:
            logger.warning(f"keyring set_password failed, falling back to settings: {e}")

    ek = EncryptionKeyRepository()
    row = ek.get_default()
    if row is None:
        return False

    try:
        from cryptography.fernet import Fernet as _F
        encrypted = _F(row.verify_blob).encrypt(master_key.encode("utf-8")).decode("ascii")
        from backend.repository.settings_repo import SettingsRepository
        SettingsRepository().set(_SETTINGS_KEY_ENCRYPTED, encrypted)
        logger.info("master_key persisted to settings table (keyring unavailable)")
        return True
    except Exception as e:
        logger.warning(f"master_key persist failed: {e}")
        return False


def _load_persisted_master_key() -> str | None:
    """从 OS keyring 或 settings 表加载 master_key。返回 None 表示无持久化数据。"""
    if _check_keyring():
        try:
            import keyring as _kr
            val = _kr.get_password(_KEYRING_SERVICE, _KEYRING_USERNAME)
            if val:
                ek = EncryptionKeyRepository()
                row = ek.get_default()
                if row and verify_master_key(val, row.salt, row.iterations, row.verify_blob):
                    logger.info("master_key restored from OS keyring")
                    return val
                else:
                    logger.warning("keyring master_key verification failed, clearing stale entry")
                    try:
                        _kr.delete_password(_KEYRING_SERVICE, _KEYRING_USERNAME)
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"keyring get_password failed: {e}")

    ek = EncryptionKeyRepository()
    row = ek.get_default()
    if row is None:
        return None

    try:
        from backend.repository.settings_repo import SettingsRepository
        encrypted = SettingsRepository().get(_SETTINGS_KEY_ENCRYPTED)
        if not encrypted:
            return None
        from cryptography.fernet import Fernet as _F
        plaintext = _F(row.verify_blob).decrypt(encrypted.encode("ascii"))
        master_key = plaintext.decode("utf-8")
        if verify_master_key(master_key, row.salt, row.iterations, row.verify_blob):
            logger.info("master_key restored from settings table")
            return master_key
        else:
            logger.warning("settings master_key verification failed, clearing stale entry")
            SettingsRepository().delete(_SETTINGS_KEY_ENCRYPTED)
    except Exception as e:
        logger.warning(f"master_key restore from settings failed: {e}")

    return None


def _clear_persisted_master_key() -> None:
    """清除持久化的 master_key (lock/reset 时调用)。"""
    if _check_keyring():
        try:
            import keyring as _kr
            _kr.delete_password(_KEYRING_SERVICE, _KEYRING_USERNAME)
        except Exception:
            pass
    try:
        from backend.repository.settings_repo import SettingsRepository
        SettingsRepository().delete(_SETTINGS_KEY_ENCRYPTED)
    except Exception:
        pass


def try_auto_unlock() -> bool:
    """启动时尝试从持久化存储恢复 unlock 状态。返回是否成功。"""
    master_key = _load_persisted_master_key()
    if master_key is None:
        return False
    try:
        svc = SecretsService()
        result = svc.unlock(master_key)
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
    def setup_master_key(self, master_key: str) -> dict:
        """初始化主密钥 (单次, 禁止重置)。"""
        ek = EncryptionKeyRepository()
        if ek.is_setup():
            raise InternalException("主密钥已初始化; 禁止重置 (Q1 决策)")
        row = ek.setup_default(master_key=master_key)
        return {
            "id": row.id,
            "name": row.name,
            "iterations": row.iterations,
            "created_at": row.created_at,
        }

    def is_master_key_setup(self) -> bool:
        return EncryptionKeyRepository().is_setup()

    # ------------------------------------------------------------------
    # Unlock / lock
    # ------------------------------------------------------------------
    def unlock(self, master_key: str) -> dict:
        """验证 master_key, 设置 30 分钟 unlock, 并持久化到 keychain。"""
        ek = EncryptionKeyRepository()
        row = ek.get_default()
        if row is None:
            raise InternalException("主密钥未初始化; 请先调用 setup 接口")

        if not verify_master_key(master_key, row.salt, row.iterations, row.verify_blob):
            raise InvalidMasterKeyError("主密钥错误")

        fernet_key = derive_fernet_key(master_key, row.salt, row.iterations)
        expires_at = _now_ts() + UNLOCK_TTL_SECONDS
        _unlock_state[row.id] = {
            "fernet_key": fernet_key,
            "expires_at": expires_at,
        }

        _persist_master_key(master_key)

        return {
            "encryption_key_id": row.id,
            "unlocked": True,
            "expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
            "ttl_seconds": UNLOCK_TTL_SECONDS,
        }

    def unlock_status(self) -> dict:
        ek = EncryptionKeyRepository()
        row = ek.get_default()
        if row is None:
            return {
                "setup": False,
                "unlocked": False,
                "expires_at": None,
                "remaining_seconds": 0,
            }
        _purge_expired()
        state = _unlock_state.get(row.id)
        if state is None:
            return {
                "setup": True,
                "unlocked": False,
                "expires_at": None,
                "remaining_seconds": 0,
            }
        remaining = max(0, int(state["expires_at"] - _now_ts()))
        return {
            "setup": True,
            "unlocked": True,
            "expires_at": datetime.fromtimestamp(state["expires_at"], tz=timezone.utc).isoformat(),
            "remaining_seconds": remaining,
        }

    def lock(self) -> dict:
        """立即清空 unlock 状态 + 清除持久化。"""
        _unlock_state.clear()
        _clear_persisted_master_key()
        return {"unlocked": False, "remaining_seconds": 0}

    # ------------------------------------------------------------------
    # Secret CRUD
    # ------------------------------------------------------------------
    def list_secrets(self) -> tuple[list[dict], int]:
        sr = SecretRepository()
        items, total = sr.list()
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
    ) -> dict:
        """新增 secret, 需要 master_key 当场加密。"""
        ek = EncryptionKeyRepository()
        row = ek.get_default()
        if row is None:
            raise InternalException("主密钥未初始化")

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
        )
        return item.to_dict(reveal=None)

    def update_secret(
        self,
        secret_id: int,
        *,
        name: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        master_key: Optional[str] = None,
    ) -> dict:
        """更新 secret; 改 api_key 必须传 master_key。"""
        sr = SecretRepository()
        existing = sr.get(secret_id)
        if existing is None:
            raise InternalException(f"secret {secret_id} 不存在")

        fernet_key = None
        if api_key is not None and api_key.strip():
            if not master_key:
                raise InternalException("修改 api_key 必须提供 master_key")
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
        )
        return item.to_dict(reveal=None)

    def delete_secret(self, secret_id: int) -> bool:
        return SecretRepository().delete(secret_id)

    # ------------------------------------------------------------------
    # Reveal (unlock 后)
    # ------------------------------------------------------------------
    def reveal(self, secret_id: int) -> dict:
        """在 unlock 状态下返回明文 api_key。"""
        ek = EncryptionKeyRepository()
        sr = SecretRepository()
        item = sr.get(secret_id)
        if item is None:
            raise InternalException(f"secret {secret_id} 不存在")

        if not _is_unlocked(item.encryption_key_id):
            raise InternalException("未解锁; 请先调用 unlock 输入主密钥")

        fernet_key = _unlock_state[item.encryption_key_id]["fernet_key"]
        try:
            plaintext = decrypt_api_key(fernet_key, item.api_key_encrypted)
        except InvalidMasterKeyError as e:
            raise InternalException(f"解密失败: {e}") from e

        return {
            "id": item.id,
            "name": item.name,
            "model": item.model,
            "base_url": item.base_url,
            "api_key": plaintext,
            "unlocked": True,
        }

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
            raise InternalException(f"secret {secret_id} 不存在")
        if not _is_unlocked(item.encryption_key_id):
            raise InternalException("未解锁; 请先调用 unlock 输入主密钥")
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
        last_error: Optional[str] = None
        last_status: Optional[int] = None
        model_count: Optional[int] = None

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
            raise InternalException("主密钥未初始化")
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
                    "api_key": decrypt_api_key(fernet_key, it.api_key_encrypted),
                }
                for it in items
            ],
        }
        plaintext = json.dumps(plaintext_dict, ensure_ascii=False, indent=2).encode("utf-8")
        cipher = fernet_key  # fernet_key is bytes; Fernet expects base64 str
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
            raise InternalException("主密钥未初始化")
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
        from cryptography.fernet import Fernet as _F, InvalidToken
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
                api_key = str(s["api_key"])
                if name in existing_by_name:
                    sr.update(
                        existing_by_name[name].id,
                        name=name,
                        model=model,
                        base_url=base_url,
                        api_key=api_key,
                        fernet_key=fernet_key,
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


__all__ = ["SecretsService", "UNLOCK_TTL_SECONDS", "_unlock_state"]
