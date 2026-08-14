"""Phase 42 跨端配置同步 service: bundle 构建 + 3-way merge + push/pull/bidirectional。

设计要点
--------

**bundle schema v1**::

    {
        "version": "1.0",
        "device_id": "uuid-xxx",          # 哪台机器生成的
        "merged_at": "2026-07-09T10:30:00Z",
        "records": {
            "favorites":      [{...}],
            "todos":          [{...}],
            "skills":         [{...}],
            "custom_sources": [{...}],
            "settings":       {"k": "v", ...},
            "secrets":        [{name, model, base_url, api_key_ciphertext_b64, ...}],
        }
    }

**3-way merge (Q3 决策)**
- ``base`` = :class:`SyncStateRepository` 存的「上次同步后的 merged bundle」
- ``local`` = 本机 :meth:`build_bundle`
- ``remote`` = 远端下载解密的 bundle
- 逐表 (favorites / todos / skills / custom_sources / settings / secrets) 合并
  策略: 记录级用「primary key / 业务键」对齐, 字段级用 ``updated_at`` 做
  last-write-wins; 冲突时 ``updated_at`` 较新的一边胜出, 计数 +1
  (审计用, 不阻塞)
- merge 完成后回写 :class:`SyncStateRepository`, 远端 push

**加密 (Q5 决策)**
- secrets 的 ``api_key`` 字段在 llm_secrets 表是 Fernet 密文 (用 master_key 派生 key)
- 跨端时, 我们直接 export **密文** 本身 (因为远端机用同一 master_key 即可解密)
- 整个 bundle 再额外加密一层 (Q4 决策: 用 master_key), 防止 WebDAV 服务商偷看
- 解密时: master_key → Fernet key → bundle 明文 → apply (api_key 仍是密文,
  落库时用现有 fernet_key 二次加密, 因为 salt/iterations 在各机器一致)

**webdav password** 独立加密 (Q1 决策, 已在 sync_configs.webdav_password_*
  实现, 不依赖 master_key)
"""
from __future__ import annotations

import base64
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from backend.crypto import (
    DEFAULT_ITERATIONS,
    decrypt_api_key,
    derive_fernet_key,
    encrypt_api_key,
    verify_master_key,
)
from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.custom_source_repo import CustomSourceRepository
from backend.repository.encryption_keys_repo import EncryptionKeyRepository
from backend.repository.favorite_repo import FavoriteRepository
from backend.repository.secrets_repo import SecretRepository
from backend.repository.settings_repo import SettingsRepository
from backend.repository.skills_repo import SkillRepository
from backend.repository.sync_configs_repo import SyncConfigRepository
from backend.repository.sync_history_repo import SyncHistoryRepository
from backend.repository.sync_states_repo import SyncStateRepository
from backend.repository.todo_repo import TodoRepository
from backend.services.webdav_client import WebDAVAuthError, WebDAVClient, WebDAVError
from backend.services.sync_zip import (
    build_sync_zip,
    extract_sync_zip,
    make_zip_remote_path,
    display_name,
)
from backend.services.sync_merge import (
    MergeResult,
    three_way_merge,
)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
BUNDLE_VERSION = "1.0"

# secrets 的元数据字段 (用于 3-way merge 比对, 不含加密密文)
SECRET_MERGE_FIELDS = (
    "name", "model", "base_url", "updated_at",
)

# settings 黑名单: 永不跨端同步的 key
# - session / runtime flags / 服务端临时状态
SETTINGS_BLOCKLIST = {
    "scheduler.last_run",
    "collector.last_run",
    "trend.last_rebuild",
    "sync_runtime_lock",  # sync 自己的运行锁
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_device_id() -> str:
    return str(uuid.uuid4())


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


# ---------------------------------------------------------------------------
# SyncService
# ---------------------------------------------------------------------------
class SyncService:
    """跨端配置同步 service。

    主要入口:
    - :meth:`build_bundle`         — 读本机配置 → bundle dict
    - :meth:`apply_bundle`         — bundle dict → 写回各表
    - 3-way merge                  — 统一走 :func:`backend.services.sync_merge.three_way_merge`
    - :meth:`push` / `pull` / `bidirectional` — 完整同步流程
    """

    # ------------------------------------------------------------------
    # bundle 构建
    # ------------------------------------------------------------------
    def build_bundle(self, *, device_id: Optional[str] = None) -> dict:
        """委托给 sync_bundle.build_bundle"""
        from backend.services.sync_bundle import build_bundle as _build_bundle
        return _build_bundle(device_id=device_id)

    # ------------------------------------------------------------------
    # bundle 写回
    # ------------------------------------------------------------------
    def apply_bundle(self, bundle: dict, *, master_key: Optional[str] = None) -> dict:
        """委托给 sync_bundle.apply_bundle"""
        from backend.services.sync_bundle import apply_bundle as _apply_bundle
        return _apply_bundle(bundle, master_key=master_key)

    # ------------------------------------------------------------------
    # 加密 / 解密 bundle
    # ------------------------------------------------------------------
    def encrypt_bundle(self, bundle: dict, master_key: str) -> bytes:
        """委托给 sync_bundle.encrypt_bundle"""
        from backend.services.sync_bundle import encrypt_bundle as _encrypt_bundle
        return _encrypt_bundle(bundle, master_key)

    def decrypt_bundle(self, payload: bytes, master_key: str) -> dict:
        """委托给 sync_bundle.decrypt_bundle"""
        from backend.services.sync_bundle import decrypt_bundle as _decrypt_bundle
        return _decrypt_bundle(payload, master_key)

    # ------------------------------------------------------------------
    # 同步入口
    # ------------------------------------------------------------------
    async def push(self, *, master_key: str) -> dict:
        """build → encrypt → WebDAV PUT (zip 容器) → 写 history → update last_sync。

        Phase 49: 每次同步打成 ``配置文件-YYYY-MM-DD.zip``(覆盖式),
        内含 envelope.json (Fernet 密文) + manifest.json (同步元数据)。
        """
        _assert_secrets_sync_safe()  # P1: secrets 锁定态禁止 push (防静默丢失)
        cfg_repo = SyncConfigRepository()
        cfg = cfg_repo.get_default()
        if cfg is None or not cfg.webdav_url or not cfg.webdav_username:
            raise InternalException("WebDAV 未配置; 请先在「同步设置」填写连接信息")
        # 解密 webdav password
        try:
            webdav_pwd = decrypt_api_key(
                derive_fernet_key(
                    master_key, cfg.webdav_password_salt, cfg.webdav_password_iters
                ),
                cfg.webdav_password_encrypted,
            )
        except Exception as e:
            raise InternalException(f"webdav password 解密失败: {e}") from e

        started_at = _now_iso()
        history = SyncHistoryRepository()
        client = WebDAVClient(
            cfg.webdav_url, cfg.webdav_username, webdav_pwd
        )

        bundle = self.build_bundle(device_id=cfg.device_id)
        envelope_bytes = self.encrypt_bundle(bundle, master_key)
        records_count = sum(
            len(bundle["records"].get(t, []))
            for t in ("favorites", "todos", "skills", "custom_sources", "secrets")
        )
        # Phase 49: 打包成 zip 容器 (同覆盖: 配置文件-YYYY-MM-DD.zip)
        # 复用 envelope.encryption 字段描述算法 (供 manifest 明文展示)
        # 解析 envelope 抽取 encryption 段
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
        # 远程路径: 自动生成覆盖式 zip 名 (不依赖 cfg.remote_path 后缀)
        # 兼容旧 cfg: 保留目录部分, 替换文件名为 zip
        base_dir = "/".join(cfg.remote_path.rsplit("/", 1)[:-1]) or "/hotspot"
        remote_path = make_zip_remote_path(base_dir)
        try:
            status = await client.upload(
                remote_path, zip_bytes, content_type="application/zip",
            )
        except WebDAVAuthError as e:
            history.write(
                config_id=cfg.id, direction="push", status="error",
                error_message=f"认证失败: {e}", started_at=started_at,
                finished_at=_now_iso(),
            )
            cfg_repo.update_last_sync(
                cfg.id, at=_now_iso(), status="error",
                error=f"webdav auth: {e}", direction="push",
            )
            raise InternalException(f"WebDAV 认证失败: {e}") from e
        except WebDAVError as e:
            history.write(
                config_id=cfg.id, direction="push", status="error",
                error_message=str(e), started_at=started_at,
                finished_at=_now_iso(),
            )
            cfg_repo.update_last_sync(
                cfg.id, at=_now_iso(), status="error",
                error=str(e), direction="push",
            )
            raise

        # 写 sync_states (用作下次 3-way merge 的 base)
        SyncStateRepository().upsert(cfg.id, json.dumps(bundle, ensure_ascii=False))

        finished_at = _now_iso()
        history.write(
            config_id=cfg.id, direction="push", status="success",
            records_count=records_count, conflict_count=0,
            started_at=started_at, finished_at=finished_at,
        )
        cfg_repo.update_last_sync(
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

    async def pull(self, *, master_key: str) -> dict:
        """GET zip → 解包 → decrypt → 3-way merge → apply → 写 history。

        Phase 49: 远端下载的是 ``配置文件-YYYY-MM-DD.zip``, 先 extract
        拿 envelope.json, 再走 Fernet decrypt + 3-way merge。
        """
        cfg_repo = SyncConfigRepository()
        cfg = cfg_repo.get_default()
        if cfg is None or not cfg.webdav_url or not cfg.webdav_username:
            raise InternalException("WebDAV 未配置; 请先在「同步设置」填写连接信息")
        from backend.crypto import decrypt_api_key
        try:
            webdav_pwd = decrypt_api_key(
                derive_fernet_key(
                    master_key, cfg.webdav_password_salt, cfg.webdav_password_iters
                ),
                cfg.webdav_password_encrypted,
            )
        except Exception as e:
            raise InternalException(f"webdav password 解密失败: {e}") from e

        started_at = _now_iso()
        history = SyncHistoryRepository()
        client = WebDAVClient(cfg.webdav_url, cfg.webdav_username, webdav_pwd)
        # 远程路径: 与 push 同步, 自动生成今日 zip
        base_dir = "/".join(cfg.remote_path.rsplit("/", 1)[:-1]) or "/hotspot"
        remote_path = make_zip_remote_path(base_dir)
        try:
            raw = await client.download(remote_path)
        except WebDAVAuthError as e:
            history.write(
                config_id=cfg.id, direction="pull", status="error",
                error_message=f"认证失败: {e}", started_at=started_at,
                finished_at=_now_iso(),
            )
            cfg_repo.update_last_sync(
                cfg.id, at=_now_iso(), status="error",
                error=f"webdav auth: {e}", direction="pull",
            )
            raise InternalException(f"WebDAV 认证失败: {e}") from e
        except WebDAVError as e:
            history.write(
                config_id=cfg.id, direction="pull", status="error",
                error_message=str(e), started_at=started_at,
                finished_at=_now_iso(),
            )
            cfg_repo.update_last_sync(
                cfg.id, at=_now_iso(), status="error",
                error=str(e), direction="pull",
            )
            raise

        if raw is None:
            # 远端无文件 → 视为空 bundle, 等价于 push
            history.write(
                config_id=cfg.id, direction="pull", status="success",
                records_count=0, conflict_count=0,
                started_at=started_at, finished_at=_now_iso(),
            )
            cfg_repo.update_last_sync(
                cfg.id, at=_now_iso(), status="success", error=None,
                direction="pull",
            )
            return {
                "direction": "pull",
                "status": "success",
                "remote_path": remote_path,
                "records_count": 0,
                "merged_at": _now_iso(),
                "message": "远端无文件, 未做合并",
            }

        # Phase 49: 解 zip 容器拿 envelope.json (兼容老格式: 纯 json 直接当 envelope)
        try:
            envelope_bytes, manifest = self._decode_remote_payload(raw)
        except Exception as e:
            history.write(
                config_id=cfg.id, direction="pull", status="error",
                error_message=f"unzip: {e}", started_at=started_at,
                finished_at=_now_iso(),
            )
            cfg_repo.update_last_sync(
                cfg.id, at=_now_iso(), status="error",
                error=f"unzip: {e}", direction="pull",
            )
            raise InternalException(f"远端包格式错: {e}") from e

        try:
            remote_bundle = self.decrypt_bundle(envelope_bytes, master_key)
        except Exception as e:
            history.write(
                config_id=cfg.id, direction="pull", status="error",
                error_message=f"decrypt: {e}", started_at=started_at,
                finished_at=_now_iso(),
            )
            cfg_repo.update_last_sync(
                cfg.id, at=_now_iso(), status="error",
                error=f"decrypt: {e}", direction="pull",
            )
            raise

        # 3-way merge
        ssr = SyncStateRepository()
        base_state = ssr.get(cfg.id)
        base_bundle = json.loads(base_state["bundle_json"]) if base_state else None
        local_bundle = self.build_bundle(device_id=cfg.device_id)
        merge_result = three_way_merge(base_bundle, local_bundle, remote_bundle)

        # apply
        self.apply_bundle(merge_result.merged_bundle, master_key=master_key)
        ssr.upsert(
            cfg.id,
            json.dumps(merge_result.merged_bundle, ensure_ascii=False),
        )

        records_count = sum(
            len(merge_result.merged_bundle["records"].get(t, []))
            for t in ("favorites", "todos", "skills", "custom_sources", "secrets")
        )
        finished_at = _now_iso()
        history.write(
            config_id=cfg.id, direction="pull", status="success",
            records_count=records_count, conflict_count=merge_result.conflict_count,
            started_at=started_at, finished_at=finished_at,
        )
        cfg_repo.update_last_sync(
            cfg.id, at=finished_at, status="success", error=None, direction="pull",
        )
        return {
            "direction": "pull",
            "status": "success",
            "remote_path": remote_path,
            "remote_manifest": manifest,  # Phase 49: 远端包 manifest (debug 用)
            "records_count": records_count,
            "conflict_count": merge_result.conflict_count,
            "table_conflicts": merge_result.table_conflicts,
            "merged_at": merge_result.merged_bundle["merged_at"],
            "remote_device_id": remote_bundle.get("device_id"),
        }

    @staticmethod
    def _decode_remote_payload(raw: bytes) -> tuple[bytes, Optional[dict]]:
        """解包远端 raw bytes → (envelope_bytes, manifest)。

        支持:
        - zip 容器 (Phase 49 新格式): 内含 envelope.json + manifest.json
        - 纯 json envelope (Phase 42 旧格式): 兼容读取
        """
        # 先尝试 zip
        if raw.startswith(b"PK"):  # ZIP 文件魔数
            envelope_bytes, manifest = extract_sync_zip(raw)
            return envelope_bytes, manifest
        # 否则当 json envelope 直接返回
        try:
            json.loads(raw.decode("utf-8"))
        except Exception as e:
            raise ValueError(f"既不是 zip 也不是合法 json: {e}") from e
        return raw, None

    async def bidirectional(self, *, master_key: str) -> dict:
        """拉远端 → 对比 → 拉或推。

        简化策略:
        - 拉远端 → 不存在 → 直接 push
        - 远端 ``merged_at`` 较新 → pull (3-way merge)
        - 本地 ``merged_at`` 较新 → push
        - 时间相同 → 默认 push

        Phase 49: 远端走 zip 路径(与 push/pull 一致), 下载后用 ``_decode_remote_payload`` 兼容。
        """
        cfg_repo = SyncConfigRepository()
        cfg = cfg_repo.get_default()
        if cfg is None or not cfg.webdav_url or not cfg.webdav_username:
            raise InternalException("WebDAV 未配置")
        webdav_pwd = decrypt_api_key(
            derive_fernet_key(
                master_key, cfg.webdav_password_salt, cfg.webdav_password_iters
            ),
            cfg.webdav_password_encrypted,
        )
        client = WebDAVClient(cfg.webdav_url, cfg.webdav_username, webdav_pwd)
        base_dir = "/".join(cfg.remote_path.rsplit("/", 1)[:-1]) or "/hotspot"
        remote_path = make_zip_remote_path(base_dir)
        raw = await client.download(remote_path)
        if raw is None:
            return await self.push(master_key=master_key)
        try:
            envelope_bytes, _ = self._decode_remote_payload(raw)
            remote_bundle = self.decrypt_bundle(envelope_bytes, master_key)
        except Exception as e:
            raise InternalException(f"远端 bundle 解密失败: {e}") from e

        local = self.build_bundle(device_id=cfg.device_id)
        local_ts = local.get("merged_at") or ""
        remote_ts = remote_bundle.get("merged_at") or ""
        if remote_ts > local_ts:
            return await self.pull(master_key=master_key)
        # P1: 本地较新 → 不能盲覆盖远端 (后 push 者整体覆盖会丢对方新增)。
        # 先 pull (3-way merge 把远端变更吸收进本地), 再把合并后的本地
        # 作为新 bundle push —— 远端变更永不丢失。
        await self.pull(master_key=master_key)
        return await self.push(master_key=master_key)

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
        started_at = _now_iso()
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
                finished_at=_now_iso(),
            )
            cfg_repo.update_last_sync(
                cfg.id, at=_now_iso(), status="error",
                error=f"webdav auth: {e}", direction="bidirectional",
            )
            raise InternalException(f"WebDAV 认证失败: {e}") from e
        except WebDAVError as e:
            history.write(
                config_id=cfg.id, direction="bidirectional", status="error",
                error_message=str(e), started_at=started_at,
                finished_at=_now_iso(),
            )
            cfg_repo.update_last_sync(
                cfg.id, at=_now_iso(), status="error",
                error=str(e), direction="bidirectional",
            )
            raise
        except Exception as e:
            history.write(
                config_id=cfg.id, direction="bidirectional", status="error",
                error_message=str(e), started_at=started_at,
                finished_at=_now_iso(),
            )
            cfg_repo.update_last_sync(
                cfg.id, at=_now_iso(), status="error",
                error=str(e), direction="bidirectional",
            )
            raise

    async def _push_with_fernet_key(
        self, fernet_key: bytes, cfg, client: WebDAVClient,
        history: SyncHistoryRepository, started_at: str,
    ) -> dict:
        """push 的 fernet_key 内部版本。

        Phase 49 改进: 每次同步打成 ``配置文件-YYYY-MM-DD.zip``(覆盖式),
        内含 envelope.json (Fernet 密文) + manifest.json (同步元数据)。
        """
        _assert_secrets_sync_safe()  # P1: secrets 锁定态禁止 push (防静默丢失)
        from cryptography.fernet import Fernet as _F
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
        # 兼容旧 cfg: 保留目录部分, 替换文件名为 zip
        base_dir = "/".join(cfg.remote_path.rsplit("/", 1)[:-1]) or "/hotspot"
        remote_path = make_zip_remote_path(base_dir)
        status = await client.upload(
            remote_path, zip_bytes, content_type="application/zip",
        )
        SyncStateRepository().upsert(cfg.id, json.dumps(bundle, ensure_ascii=False))
        finished_at = _now_iso()
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
        finished_at = _now_iso()
        history.write(
            config_id=cfg.id, direction="pull", status="success",
            records_count=records_count, conflict_count=merge_result.conflict_count,
            started_at=started_at, finished_at=finished_at,
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

    def decrypt_bundle_with_fernet_key(self, payload: bytes, fernet_key: bytes) -> dict:
        """委托给 sync_bundle.decrypt_bundle_with_fernet_key"""
        from backend.services.sync_bundle import decrypt_bundle_with_fernet_key as _decrypt
        return _decrypt(payload, fernet_key)

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------
    def status(self) -> dict:
        cfg_repo = SyncConfigRepository()
        cfg = cfg_repo.get_default()
        if cfg is None:
            return {"configured": False}
        # Phase 49: 暴露实际同步用 zip 路径 + manifest display_name (中文) 供前端展示
        base_dir = "/".join(cfg.remote_path.rsplit("/", 1)[:-1]) or "/hotspot"
        return {
            "configured": True,
            "webdav_url": cfg.webdav_url,
            "webdav_username": cfg.webdav_username,
            "remote_path": cfg.remote_path,  # 用户配置的 base_dir
            "effective_remote_path": make_zip_remote_path(base_dir),  # 实际 zip 路径 (ASCII)
            "effective_display_name": display_name(),  # manifest display_name (中文)
            "auto_sync_enabled": bool(cfg.auto_sync_enabled),
            "auto_sync_interval_minutes": cfg.auto_sync_interval_minutes,
            "last_sync_at": cfg.last_sync_at,
            "last_sync_status": cfg.last_sync_status,
            "last_sync_error": cfg.last_sync_error,
            "last_sync_direction": cfg.last_sync_direction,
            "device_id": cfg.device_id,
            "created_at": cfg.created_at,
            "updated_at": cfg.updated_at,
        }

    def history(self, limit: int = 50) -> list[dict]:
        cfg_repo = SyncConfigRepository()
        cfg = cfg_repo.get_default()
        if cfg is None:
            return []
        return SyncHistoryRepository().list_recent(cfg.id, limit=limit)


__all__ = [
    "SyncService",
    "MergeResult",
    "BUNDLE_VERSION",
    "SETTINGS_BLOCKLIST",
]
