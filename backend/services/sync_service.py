"""SyncService — cross-device config sync orchestration (push/pull/bidirectional).

Uses :mod:`sync_merge` for 3-way merge and :mod:`sync_bundle` for serialization.
"""

from __future__ import annotations

import json

from backend.crypto import decrypt_api_key, derive_fernet_key
from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.encryption_keys_repo import EncryptionKeyRepository
from backend.repository.sync_configs_repo import SyncConfigRepository
from backend.repository.sync_history_repo import SyncHistoryRepository
from backend.repository.sync_states_repo import SyncStateRepository
from backend.services.sync_bundle import (
    apply_bundle,
    build_bundle,
    decrypt_bundle,
    decrypt_bundle_with_fernet_key,
    decode_remote_payload,
    encrypt_bundle,
)
from backend.services.sync_merge import (
    MergeResult,
    _now_iso,
    three_way_merge,
)
from backend.services.sync_zip import (
    build_sync_zip,
    make_zip_remote_path,
    display_name,
)
from backend.services.webdav_client import WebDAVAuthError, WebDAVClient, WebDAVError


class SyncService:
    """Cross-device config sync service.

    Main entry points:
    - :meth:`push` / :meth:`pull` / :meth:`bidirectional` — full sync workflows
    - :meth:`status` / :meth:`history` — query
    """

    # ------------------------------------------------------------------
    # Push
    # ------------------------------------------------------------------
    async def push(self, *, master_key: str) -> dict:
        """build → encrypt → WebDAV PUT (zip) → write history."""
        cfg_repo = SyncConfigRepository()
        cfg = cfg_repo.get_default()
        if cfg is None or not cfg.webdav_url or not cfg.webdav_username:
            raise InternalException("WebDAV 未配置; 请先在「同步设置」填写连接信息")
        try:
            webdav_pwd = decrypt_api_key(
                derive_fernet_key(master_key, cfg.webdav_password_salt, cfg.webdav_password_iters),
                cfg.webdav_password_encrypted,
            )
        except Exception as e:
            raise InternalException(f"webdav password 解密失败: {e}") from e

        started_at = _now_iso()
        history = SyncHistoryRepository()
        client = WebDAVClient(cfg.webdav_url, cfg.webdav_username, webdav_pwd)

        bundle = build_bundle(device_id=cfg.device_id)
        envelope_bytes = encrypt_bundle(bundle, master_key)
        records_count = sum(
            len(bundle["records"].get(t, []))
            for t in ("favorites", "todos", "skills", "custom_sources", "secrets")
        )
        try:
            envelope_obj = json.loads(envelope_bytes.decode("utf-8"))
            encryption = envelope_obj.get("encryption", {})
        except Exception:
            encryption = {}
        zip_bytes = build_sync_zip(
            envelope_bytes=envelope_bytes,
            device_id=bundle.get("device_id", ""),
            merged_at=bundle.get("merged_at", ""),
            direction="push",
            records_count=records_count,
            conflict_count=0,
            encryption=encryption,
        )
        base_dir = "/".join(cfg.remote_path.rsplit("/", 1)[:-1]) or "/hotspot"
        remote_path = make_zip_remote_path(base_dir)
        try:
            status = await client.upload(remote_path, zip_bytes, content_type="application/zip")
        except WebDAVAuthError as e:
            history.write(config_id=cfg.id, direction="push", status="error",
                          error_message=f"认证失败: {e}", started_at=started_at, finished_at=_now_iso())
            cfg_repo.update_last_sync(cfg.id, at=_now_iso(), status="error", error=f"webdav auth: {e}", direction="push")
            raise InternalException(f"WebDAV 认证失败: {e}") from e
        except WebDAVError as e:
            history.write(config_id=cfg.id, direction="push", status="error",
                          error_message=str(e), started_at=started_at, finished_at=_now_iso())
            cfg_repo.update_last_sync(cfg.id, at=_now_iso(), status="error", error=str(e), direction="push")
            raise

        SyncStateRepository().upsert(cfg.id, json.dumps(bundle, ensure_ascii=False))
        finished_at = _now_iso()
        history.write(config_id=cfg.id, direction="push", status="success",
                       records_count=records_count, conflict_count=0,
                       started_at=started_at, finished_at=finished_at)
        cfg_repo.update_last_sync(cfg.id, at=finished_at, status="success", error=None, direction="push")
        return {
            "direction": "push", "status": "success", "status_code": status,
            "records_count": records_count, "remote_path": remote_path,
            "device_id": cfg.device_id, "merged_at": bundle["merged_at"],
        }

    # ------------------------------------------------------------------
    # Pull
    # ------------------------------------------------------------------
    async def pull(self, *, master_key: str) -> dict:
        """GET zip → unzip → decrypt → 3-way merge → apply → write history."""
        cfg_repo = SyncConfigRepository()
        cfg = cfg_repo.get_default()
        if cfg is None or not cfg.webdav_url or not cfg.webdav_username:
            raise InternalException("WebDAV 未配置; 请先在「同步设置」填写连接信息")
        try:
            webdav_pwd = decrypt_api_key(
                derive_fernet_key(master_key, cfg.webdav_password_salt, cfg.webdav_password_iters),
                cfg.webdav_password_encrypted,
            )
        except Exception as e:
            raise InternalException(f"webdav password 解密失败: {e}") from e

        started_at = _now_iso()
        history = SyncHistoryRepository()
        client = WebDAVClient(cfg.webdav_url, cfg.webdav_username, webdav_pwd)
        base_dir = "/".join(cfg.remote_path.rsplit("/", 1)[:-1]) or "/hotspot"
        remote_path = make_zip_remote_path(base_dir)
        try:
            raw = await client.download(remote_path)
        except WebDAVAuthError as e:
            history.write(config_id=cfg.id, direction="pull", status="error",
                          error_message=f"认证失败: {e}", started_at=started_at, finished_at=_now_iso())
            cfg_repo.update_last_sync(cfg.id, at=_now_iso(), status="error", error=f"webdav auth: {e}", direction="pull")
            raise InternalException(f"WebDAV 认证失败: {e}") from e
        except WebDAVError as e:
            history.write(config_id=cfg.id, direction="pull", status="error",
                          error_message=str(e), started_at=started_at, finished_at=_now_iso())
            cfg_repo.update_last_sync(cfg.id, at=_now_iso(), status="error", error=str(e), direction="pull")
            raise

        if raw is None:
            history.write(config_id=cfg.id, direction="pull", status="success",
                           records_count=0, conflict_count=0, started_at=started_at, finished_at=_now_iso())
            cfg_repo.update_last_sync(cfg.id, at=_now_iso(), status="success", error=None, direction="pull")
            return {"direction": "pull", "status": "success", "remote_path": remote_path,
                    "records_count": 0, "merged_at": _now_iso(), "message": "远端无文件, 未做合并"}

        try:
            envelope_bytes, manifest = decode_remote_payload(raw)
        except Exception as e:
            history.write(config_id=cfg.id, direction="pull", status="error",
                          error_message=f"unzip: {e}", started_at=started_at, finished_at=_now_iso())
            cfg_repo.update_last_sync(cfg.id, at=_now_iso(), status="error", error=f"unzip: {e}", direction="pull")
            raise InternalException(f"远端包格式错: {e}") from e

        try:
            remote_bundle = decrypt_bundle(envelope_bytes, master_key)
        except Exception as e:
            history.write(config_id=cfg.id, direction="pull", status="error",
                          error_message=f"decrypt: {e}", started_at=started_at, finished_at=_now_iso())
            cfg_repo.update_last_sync(cfg.id, at=_now_iso(), status="error", error=f"decrypt: {e}", direction="pull")
            raise

        ssr = SyncStateRepository()
        base_state = ssr.get(cfg.id)
        base_bundle = json.loads(base_state["bundle_json"]) if base_state else None
        local_bundle = build_bundle(device_id=cfg.device_id)
        merge_result = three_way_merge(base_bundle, local_bundle, remote_bundle)

        apply_bundle(merge_result.merged_bundle, master_key=master_key)
        ssr.upsert(cfg.id, json.dumps(merge_result.merged_bundle, ensure_ascii=False))

        records_count = sum(
            len(merge_result.merged_bundle["records"].get(t, []))
            for t in ("favorites", "todos", "skills", "custom_sources", "secrets")
        )
        finished_at = _now_iso()
        history.write(config_id=cfg.id, direction="pull", status="success",
                       records_count=records_count, conflict_count=merge_result.conflict_count,
                       started_at=started_at, finished_at=finished_at)
        cfg_repo.update_last_sync(cfg.id, at=finished_at, status="success", error=None, direction="pull")
        return {
            "direction": "pull", "status": "success", "remote_path": remote_path,
            "remote_manifest": manifest, "records_count": records_count,
            "conflict_count": merge_result.conflict_count,
            "table_conflicts": merge_result.table_conflicts,
            "merged_at": merge_result.merged_bundle["merged_at"],
            "remote_device_id": remote_bundle.get("device_id"),
        }

    # ------------------------------------------------------------------
    # Bidirectional
    # ------------------------------------------------------------------
    async def bidirectional(self, *, master_key: str) -> dict:
        """Pull remote → compare merged_at → pull (remote newer) or push (local newer)."""
        cfg_repo = SyncConfigRepository()
        cfg = cfg_repo.get_default()
        if cfg is None or not cfg.webdav_url or not cfg.webdav_username:
            raise InternalException("WebDAV 未配置")
        webdav_pwd = decrypt_api_key(
            derive_fernet_key(master_key, cfg.webdav_password_salt, cfg.webdav_password_iters),
            cfg.webdav_password_encrypted,
        )
        client = WebDAVClient(cfg.webdav_url, cfg.webdav_username, webdav_pwd)
        base_dir = "/".join(cfg.remote_path.rsplit("/", 1)[:-1]) or "/hotspot"
        remote_path = make_zip_remote_path(base_dir)
        raw = await client.download(remote_path)
        if raw is None:
            return await self.push(master_key=master_key)
        try:
            envelope_bytes, _ = decode_remote_payload(raw)
            remote_bundle = decrypt_bundle(envelope_bytes, master_key)
        except Exception as e:
            raise InternalException(f"远端 bundle 解密失败: {e}") from e

        local = build_bundle(device_id=cfg.device_id)
        local_ts = local.get("merged_at") or ""
        remote_ts = remote_bundle.get("merged_at") or ""
        if remote_ts > local_ts:
            return await self.pull(master_key=master_key)
        return await self.push(master_key=master_key)

    async def bidirectional_with_fernet_key(self, fernet_key: bytes) -> dict:
        """Bidirectional sync using pre-derived fernet_key (scheduler auto-sync)."""
        cfg_repo = SyncConfigRepository()
        cfg = cfg_repo.get_default()
        if cfg is None or not cfg.webdav_url or not cfg.webdav_username:
            raise InternalException("WebDAV 未配置")
        try:
            webdav_pwd = decrypt_api_key(fernet_key, cfg.webdav_password_encrypted)
        except Exception as e:
            raise InternalException(f"webdav password 解密失败: {e}") from e

        from cryptography.fernet import Fernet as _F

        client = WebDAVClient(cfg.webdav_url, cfg.webdav_username, webdav_pwd)
        history = SyncHistoryRepository()
        started_at = _now_iso()
        base_dir = "/".join(cfg.remote_path.rsplit("/", 1)[:-1]) or "/hotspot"
        remote_path = make_zip_remote_path(base_dir)
        try:
            raw = await client.download(remote_path)
            if raw is None:
                return await self._push_with_fernet_key(fernet_key, cfg, client, history, started_at)
            envelope_bytes, _ = decode_remote_payload(raw)
            remote_bundle = decrypt_bundle_with_fernet_key(envelope_bytes, fernet_key)
            local = build_bundle(device_id=cfg.device_id)
            local_ts = local.get("merged_at") or ""
            remote_ts = remote_bundle.get("merged_at") or ""
            if remote_ts > local_ts:
                return await self._pull_with_fernet_key(fernet_key, cfg, client, history, started_at, raw, remote_bundle)
            return await self._push_with_fernet_key(fernet_key, cfg, client, history, started_at)
        except WebDAVAuthError as e:
            history.write(config_id=cfg.id, direction="bidirectional", status="error",
                          error_message=f"认证失败: {e}", started_at=started_at, finished_at=_now_iso())
            cfg_repo.update_last_sync(cfg.id, at=_now_iso(), status="error", error=f"webdav auth: {e}", direction="bidirectional")
            raise InternalException(f"WebDAV 认证失败: {e}") from e
        except WebDAVError as e:
            history.write(config_id=cfg.id, direction="bidirectional", status="error",
                          error_message=str(e), started_at=started_at, finished_at=_now_iso())
            cfg_repo.update_last_sync(cfg.id, at=_now_iso(), status="error", error=str(e), direction="bidirectional")
            raise
        except Exception as e:
            history.write(config_id=cfg.id, direction="bidirectional", status="error",
                          error_message=str(e), started_at=started_at, finished_at=_now_iso())
            cfg_repo.update_last_sync(cfg.id, at=_now_iso(), status="error", error=str(e), direction="bidirectional")
            raise

    async def _push_with_fernet_key(self, fernet_key: bytes, cfg, client: WebDAVClient,
                                     history: SyncHistoryRepository, started_at: str) -> dict:
        from cryptography.fernet import Fernet as _F
        bundle = build_bundle(device_id=cfg.device_id)
        plaintext = json.dumps(bundle, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ct = _F(fernet_key).encrypt(plaintext)
        ek_repo = EncryptionKeyRepository()
        ek_row = ek_repo.get_default()
        from backend.services.sync_merge import BUNDLE_VERSION
        envelope = {
            "version": BUNDLE_VERSION,
            "encryption": {"algorithm": "Fernet", "kdf": "PBKDF2-HMAC-SHA256",
                           "iterations": ek_row.iterations if ek_row else 0,
                           "salt_b64": ek_row.salt.hex() if ek_row else ""},
            "encryption_kind": "sync-bundle",
            "merged_at": bundle.get("merged_at"), "device_id": bundle.get("device_id"),
            "ciphertext_b64": ct.hex(),
        }
        envelope_bytes = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        records_count = sum(len(bundle["records"].get(t, [])) for t in ("favorites", "todos", "skills", "custom_sources", "secrets"))
        zip_bytes = build_sync_zip(envelope_bytes=envelope_bytes, device_id=bundle.get("device_id", ""),
                                    merged_at=bundle.get("merged_at", ""), direction="push",
                                    records_count=records_count, conflict_count=0, encryption=envelope["encryption"])
        base_dir = "/".join(cfg.remote_path.rsplit("/", 1)[:-1]) or "/hotspot"
        remote_path = make_zip_remote_path(base_dir)
        status = await client.upload(remote_path, zip_bytes, content_type="application/zip")
        SyncStateRepository().upsert(cfg.id, json.dumps(bundle, ensure_ascii=False))
        finished_at = _now_iso()
        history.write(config_id=cfg.id, direction="push", status="success",
                       records_count=records_count, conflict_count=0, started_at=started_at, finished_at=finished_at)
        SyncConfigRepository().update_last_sync(cfg.id, at=finished_at, status="success", error=None, direction="push")
        return {"direction": "push", "status": "success", "status_code": status,
                "records_count": records_count, "remote_path": remote_path,
                "device_id": cfg.device_id, "merged_at": bundle["merged_at"]}

    async def _pull_with_fernet_key(self, fernet_key: bytes, cfg, client: WebDAVClient,
                                     history: SyncHistoryRepository, started_at: str,
                                     raw: bytes, remote_bundle: dict) -> dict:
        ssr = SyncStateRepository()
        base_state = ssr.get(cfg.id)
        base_bundle = json.loads(base_state["bundle_json"]) if base_state else None
        local_bundle = build_bundle(device_id=cfg.device_id)
        merge_result = three_way_merge(base_bundle, local_bundle, remote_bundle)
        ek_repo = EncryptionKeyRepository()
        ek_row = ek_repo.get_default()
        from backend.services.secrets_service import _unlock_state
        if ek_row is not None:
            _unlock_state[ek_row.id] = {"fernet_key": fernet_key, "expires_at": float("inf")}
        try:
            apply_bundle(merge_result.merged_bundle)
        finally:
            if ek_row is not None:
                _unlock_state.pop(ek_row.id, None)
        ssr.upsert(cfg.id, json.dumps(merge_result.merged_bundle, ensure_ascii=False))
        records_count = sum(len(merge_result.merged_bundle["records"].get(t, [])) for t in ("favorites", "todos", "skills", "custom_sources", "secrets"))
        finished_at = _now_iso()
        history.write(config_id=cfg.id, direction="pull", status="success",
                       records_count=records_count, conflict_count=merge_result.conflict_count,
                       started_at=started_at, finished_at=finished_at)
        SyncConfigRepository().update_last_sync(cfg.id, at=finished_at, status="success", error=None, direction="pull")
        return {"direction": "pull", "status": "success", "remote_path": cfg.remote_path,
                "records_count": records_count, "conflict_count": merge_result.conflict_count,
                "table_conflicts": merge_result.table_conflicts,
                "merged_at": merge_result.merged_bundle["merged_at"],
                "remote_device_id": remote_bundle.get("device_id")}

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------
    def status(self) -> dict:
        from backend.repository.sync_configs_repo import SyncConfigRepository
        cfg = SyncConfigRepository().get_default()
        if cfg is None:
            return {"configured": False}
        base_dir = "/".join(cfg.remote_path.rsplit("/", 1)[:-1]) or "/hotspot"
        return {
            "configured": True, "webdav_url": cfg.webdav_url,
            "webdav_username": cfg.webdav_username, "remote_path": cfg.remote_path,
            "effective_remote_path": make_zip_remote_path(base_dir),
            "effective_display_name": display_name(),
            "auto_sync_enabled": bool(cfg.auto_sync_enabled),
            "auto_sync_interval_minutes": cfg.auto_sync_interval_minutes,
            "last_sync_at": cfg.last_sync_at, "last_sync_status": cfg.last_sync_status,
            "last_sync_error": cfg.last_sync_error, "last_sync_direction": cfg.last_sync_direction,
            "device_id": cfg.device_id, "created_at": cfg.created_at, "updated_at": cfg.updated_at,
        }

    def history(self, limit: int = 50) -> list[dict]:
        from backend.repository.sync_configs_repo import SyncConfigRepository
        cfg = SyncConfigRepository().get_default()
        if cfg is None:
            return []
        return SyncHistoryRepository().list_recent(cfg.id, limit=limit)


__all__ = ["SyncService"]