"""P1.2: Fernet-key 同步路径 mixin。

从 sync_service.py 拆出的独立职责：**scheduler 自动同步专用**的 master_key
无关路径。与主类用 master_key 字符串不同, 这里直接用已解锁的 fernet_key
加密/解密 webdav password 和 bundle。

拆出此 mixin 让 sync_service.py 聚焦 master_key 编排, 消除两套对称逻辑
在同一类的维护负担。

依赖
----
- ``self.build_bundle()`` / ``self.apply_bundle()`` — 由 SyncService 主类提供
- ``self.decrypt_bundle_with_fernet_key()`` — 本 mixin 提供 (委托 sync_bundle)
"""
from __future__ import annotations

import json

from cryptography.fernet import Fernet as _F

from backend.exceptions import InternalException
from backend.repository.encryption_keys_repo import EncryptionKeyRepository
from backend.repository.secrets_repo import SecretRepository
from backend.repository.sync_configs_repo import SyncConfigRepository
from backend.repository.sync_history_repo import SyncHistoryRepository
from backend.repository.sync_states_repo import SyncStateRepository
from backend.services.sync_merge import three_way_merge
from backend.services.sync_service_constants import BUNDLE_VERSION, now_iso
from backend.services.sync_zip import build_sync_zip, make_zip_remote_path
from backend.services.webdav_client import WebDAVAuthError, WebDAVClient, WebDAVError


def _assert_secrets_sync_safe() -> None:
    """P1: secrets 锁定态禁止 push — 未解锁时 build_bundle 将密文置 None,
    apply_bundle 对无密文记录直接 skip, 合并层无法区分"未导出"与"已删除",
    锁定态 push 会静默丢失/覆盖对端 secrets。检测到 vault 锁定且存在
    secrets 时明确报错, 而不是静默丢数据。
    """
    from backend.services.secrets_service import _is_unlocked

    ek_row = EncryptionKeyRepository().get_default()
    if ek_row is None:
        return  # 主密钥未初始化 → 无 secrets 可同步
    if _is_unlocked(ek_row.id):
        return
    try:
        secrets, _ = SecretRepository().list()
    except Exception:
        return
    if secrets:
        raise InternalException(
            "secrets vault 未解锁, 拒绝 push: 锁定状态下 secrets 密文不会进入 "
            "同步 bundle, 会导致对端 secrets 被覆盖/丢失。请先在「密钥管理」"
            "解锁后再同步。"
        )


class FernetKeySyncMixin:
    """Fernet-key 同步路径 (scheduler 自动同步)。

    依赖 SyncService 主类提供的 build_bundle / apply_bundle;
    _now_iso / _assert_secrets_sync_safe 为模块级函数 (保持原实现)。
    """

    # 由 SyncService 主类实现
    def build_bundle(self, *, device_id: str | None = None) -> dict:
        raise NotImplementedError

    def apply_bundle(self, bundle: dict, *, master_key: str | None = None) -> dict:
        raise NotImplementedError

    def decrypt_bundle_with_fernet_key(self, payload: bytes, fernet_key: bytes) -> dict:
        """委托给 sync_bundle.decrypt_bundle_with_fernet_key"""
        from backend.services.sync_bundle import decrypt_bundle_with_fernet_key as _decrypt
        return _decrypt(payload, fernet_key)

    # ------------------------------------------------------------------
    # bidirectional (fernet_key 版本)
    # ------------------------------------------------------------------
    async def bidirectional_with_fernet_key(self, fernet_key: bytes) -> dict:
        """使用解锁后的 fernet_key 进行双向同步 (scheduler 自动同步使用)。

        与 :meth:`bidirectional` 行为一致, 区别仅在: 用 fernet_key 直接解密
        webdav password 和 bundle, 不再需要原始 master_key 字符串。
        """
        from backend.crypto import decrypt_api_key

        cfg_repo = SyncConfigRepository()
        cfg = cfg_repo.get_default()
        if cfg is None or not cfg.webdav_url or not cfg.webdav_username:
            raise InternalException("WebDAV 未配置")
        try:
            webdav_pwd = decrypt_api_key(fernet_key, cfg.webdav_password_encrypted)
        except Exception as e:
            raise InternalException(f"webdav password 解密失败: {e}") from e

        client = WebDAVClient(cfg.webdav_url, cfg.webdav_username, webdav_pwd)
        history = SyncHistoryRepository()
        started_at = now_iso()
        # Phase 49: 远端走 zip 路径 (与 push/pull 一致), base_dir 取自 cfg.remote_path
        base_dir = "/".join(cfg.remote_path.rsplit("/", 1)[:-1]) or "/hotspot"
        remote_path = make_zip_remote_path(base_dir)
        try:
            raw = await client.download(remote_path)
            if raw is None:
                # 远端无文件 → push
                result = await self._push_with_fernet_key(fernet_key, cfg, client, history, started_at)
                return result
            # Phase 49: 解 zip 容器拿 envelope.json (兼容老格式纯 json)
            envelope_bytes, _ = self._decode_remote_payload(raw)
            remote_bundle = self.decrypt_bundle_with_fernet_key(envelope_bytes, fernet_key)
            local = self.build_bundle(device_id=cfg.device_id)
            local_ts = local.get("merged_at") or ""
            remote_ts = remote_bundle.get("merged_at") or ""
            if remote_ts > local_ts:
                return await self._pull_with_fernet_key(
                    fernet_key, cfg, client, history, started_at,
                    raw, remote_bundle,
                )
            # P1: 本地较新 → 先 pull 合并远端变更再 push (消除盲覆盖)
            await self._pull_with_fernet_key(
                fernet_key, cfg, client, history, started_at,
                raw, remote_bundle,
            )
            return await self._push_with_fernet_key(
                fernet_key, cfg, client, history, started_at,
            )
        except WebDAVAuthError as e:
            history.write(
                config_id=cfg.id, direction="bidirectional", status="error",
                error_message=f"认证失败: {e}", started_at=started_at,
                finished_at=now_iso(),
            )
            cfg_repo.update_last_sync(
                cfg.id, at=now_iso(), status="error",
                error=f"webdav auth: {e}", direction="bidirectional",
            )
            raise InternalException(f"WebDAV 认证失败: {e}") from e
        except WebDAVError as e:
            history.write(
                config_id=cfg.id, direction="bidirectional", status="error",
                error_message=str(e), started_at=started_at,
                finished_at=now_iso(),
            )
            cfg_repo.update_last_sync(
                cfg.id, at=now_iso(), status="error",
                error=str(e), direction="bidirectional",
            )
            raise
        except Exception as e:
            history.write(
                config_id=cfg.id, direction="bidirectional", status="error",
                error_message=str(e), started_at=started_at,
                finished_at=now_iso(),
            )
            cfg_repo.update_last_sync(
                cfg.id, at=now_iso(), status="error",
                error=str(e), direction="bidirectional",
            )
            raise

    # ------------------------------------------------------------------
    # push (fernet_key 版本)
    # ------------------------------------------------------------------
    async def _push_with_fernet_key(
        self, fernet_key: bytes, cfg, client: WebDAVClient,
        history: SyncHistoryRepository, started_at: str,
    ) -> dict:
        """push 的 fernet_key 内部版本。"""
        _assert_secrets_sync_safe()  # P1: secrets 锁定态禁止 push (防静默丢失)
        # 解锁时把 fernet_key 视为 master_key 的派生 key;
        # bundle 的 envelope 用同一 key 加密/解密
        bundle = self.build_bundle(device_id=cfg.device_id)
        plaintext = json.dumps(bundle, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ct = _F(fernet_key).encrypt(plaintext)
        ek_repo = EncryptionKeyRepository()
        ek_row = ek_repo.get_default()
        envelope = {
            "version": BUNDLE_VERSION,
            "encryption": {
                "algorithm": "Fernet",
                "kdf": "PBKDF2-HMAC-SHA256",
                "iterations": ek_row.iterations if ek_row else 0,
                "salt_b64": ek_row.salt.hex() if ek_row else "",
            },
            "encryption_kind": "sync-bundle",
            "merged_at": bundle.get("merged_at"),
            "device_id": bundle.get("device_id"),
            "ciphertext_b64": ct.hex(),
        }
        envelope_bytes = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        records_count = sum(
            len(bundle["records"].get(t, []))
            for t in ("favorites", "todos", "skills", "custom_sources", "secrets")
        )
        # Phase 49: 打包成 zip 容器 (同覆盖: 配置文件-YYYY-MM-DD.zip)
        zip_bytes = build_sync_zip(
            envelope_bytes=envelope_bytes,
            device_id=bundle.get("device_id", ""),
            merged_at=bundle.get("merged_at", ""),
            direction="push",
            records_count=records_count,
            conflict_count=0,
            encryption=envelope["encryption"],
        )
        # 远程路径: 自动生成覆盖式 zip 名 (不依赖 cfg.remote_path 后缀)
        base_dir = "/".join(cfg.remote_path.rsplit("/", 1)[:-1]) or "/hotspot"
        remote_path = make_zip_remote_path(base_dir)
        status = await client.upload(
            remote_path, zip_bytes, content_type="application/zip",
        )
        SyncStateRepository().upsert(cfg.id, json.dumps(bundle, ensure_ascii=False))
        finished_at = now_iso()
        history.write(
            config_id=cfg.id, direction="push", status="success",
            records_count=records_count, conflict_count=0,
            started_at=started_at, finished_at=finished_at,
        )
        SyncConfigRepository().update_last_sync(
            cfg.id, at=finished_at, status="success", error=None, direction="push",
        )
        return {
            "direction": "push",
            "status": "success",
            "status_code": status,
            "records_count": records_count,
            "remote_path": remote_path,
            "device_id": cfg.device_id,
            "merged_at": bundle["merged_at"],
        }

    # ------------------------------------------------------------------
    # pull (fernet_key 版本)
    # ------------------------------------------------------------------
    async def _pull_with_fernet_key(
        self, fernet_key: bytes, cfg, client: WebDAVClient,
        history: SyncHistoryRepository, started_at: str,
        raw: bytes, remote_bundle: dict,
    ) -> dict:
        """pull 的 fernet_key 内部版本。"""
        ssr = SyncStateRepository()
        base_state = ssr.get(cfg.id)
        base_bundle = json.loads(base_state["bundle_json"]) if base_state else None
        local_bundle = self.build_bundle(device_id=cfg.device_id)
        merge_result = three_way_merge(base_bundle, local_bundle, remote_bundle)
        # apply (使用 fernet_key 而非 master_key, 派生同样的 key)
        ek_repo = EncryptionKeyRepository()
        ek_row = ek_repo.get_default()
        # 临时将 fernet_key 注入 unlock state 让 secrets 部分能用
        from backend.services.secrets_service import _unlock_state
        if ek_row is not None:
            _unlock_state[ek_row.id] = {
                "fernet_key": fernet_key,
                "expires_at": float("inf"),  # 临时, 调用完清掉
            }
        try:
            self.apply_bundle(merge_result.merged_bundle)
        finally:
            if ek_row is not None:
                _unlock_state.pop(ek_row.id, None)
        ssr.upsert(
            cfg.id,
            json.dumps(merge_result.merged_bundle, ensure_ascii=False),
        )
        records_count = sum(
            len(merge_result.merged_bundle["records"].get(t, []))
            for t in ("favorites", "todos", "skills", "custom_sources", "secrets")
        )
        finished_at = now_iso()
        history.write(
            config_id=cfg.id, direction="pull", status="success",
            records_count=records_count, conflict_count=merge_result.conflict_count,
            started_at=started_at, finished_at=finished_at,
            table_conflicts=(
                json.dumps(merge_result.table_conflicts, ensure_ascii=False)
                if merge_result.table_conflicts else None
            ),
        )
        SyncConfigRepository().update_last_sync(
            cfg.id, at=finished_at, status="success", error=None, direction="pull",
        )
        return {
            "direction": "pull",
            "status": "success",
            "remote_path": cfg.remote_path,
            "records_count": records_count,
            "conflict_count": merge_result.conflict_count,
            "table_conflicts": merge_result.table_conflicts,
            "merged_at": merge_result.merged_bundle["merged_at"],
            "remote_device_id": remote_bundle.get("device_id"),
        }


__all__ = ["FernetKeySyncMixin"]