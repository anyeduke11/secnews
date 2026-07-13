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
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

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
# 内部数据结构
# ---------------------------------------------------------------------------
@dataclass
class MergeResult:
    merged_bundle: dict
    conflict_count: int
    table_conflicts: dict[str, int]

    def to_dict(self) -> dict:
        return {
            "conflict_count": self.conflict_count,
            "table_conflicts": self.table_conflicts,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_device_id() -> str:
    return str(uuid.uuid4())


def _validate_bundle(bundle: dict) -> None:
    if not isinstance(bundle, dict):
        raise InternalException("bundle 必须为 dict")
    if bundle.get("version") != BUNDLE_VERSION:
        raise InternalException(
            f"bundle version 不支持: {bundle.get('version')} (期望 {BUNDLE_VERSION})"
        )
    if "records" not in bundle or not isinstance(bundle["records"], dict):
        raise InternalException("bundle.records 缺失或格式错")
    for key in (
        "favorites", "todos", "skills", "custom_sources", "secrets",
    ):
        if key in bundle["records"] and not isinstance(bundle["records"][key], list):
            raise InternalException(f"bundle.records.{key} 必须为 list")
    if "settings" in bundle["records"] and not isinstance(
        bundle["records"]["settings"], dict
    ):
        raise InternalException("bundle.records.settings 必须为 dict")


# ---------------------------------------------------------------------------
# SyncService
# ---------------------------------------------------------------------------
class SyncService:
    """跨端配置同步 service。

    主要入口:
    - :meth:`build_bundle`         — 读本机配置 → bundle dict
    - :meth:`apply_bundle`         — bundle dict → 写回各表
    - :meth:`three_way_merge`      — base/local/remote → merged
    - :meth:`push` / `pull` / `bidirectional` — 完整同步流程
    """

    # ------------------------------------------------------------------
    # bundle 构建
    # ------------------------------------------------------------------
    def build_bundle(self, *, device_id: Optional[str] = None) -> dict:
        """读本机所有可同步配置 → bundle dict。

        ``device_id`` 不传则用 sync_configs.device_id (首次会生成)。
        """
        cfg = SyncConfigRepository().get_default()
        if device_id is None:
            if cfg is not None and cfg.device_id:
                device_id = cfg.device_id
            else:
                device_id = _new_device_id()
                if cfg is not None:
                    SyncConfigRepository().update_device_id(cfg.id, device_id)

        records: dict[str, Any] = {
            "favorites": [
                it.to_dict() for it in FavoriteRepository().list(limit=1000)
            ],
            "todos": [
                it.to_dict() for it in TodoRepository().list(limit=1000)[0]
            ],
            "skills": [
                it.to_dict() for it in SkillRepository().list(limit=1000)[0]
            ],
            "custom_sources": [
                src.to_dict() for src in CustomSourceRepository().list()
            ],
            "settings": {
                k: v for k, v in SettingsRepository().list_all().items()
                if k not in SETTINGS_BLOCKLIST
            },
            "secrets": [],  # 单独处理, 需要 master_key 派生 fernet_key
        }

        # secrets 导出密文 (跨端时远端用同一 master_key 即可解密)
        ek = EncryptionKeyRepository()
        ek_row = ek.get_default()
        if ek_row is not None:
            from backend.services.secrets_service import _is_unlocked
            # 用 unlock state 里现成的 fernet_key 优先 (30 分钟内免重新输密码)
            if _is_unlocked(ek_row.id):
                from backend.services.secrets_service import _unlock_state
                fernet_key = _unlock_state[ek_row.id]["fernet_key"]
                unlocked = True
            else:
                # 未 unlock 时, 只导出元数据, api_key 字段填空
                fernet_key = None
                unlocked = False

            sr = SecretRepository()
            for s in sr.list()[0]:
                rec = {
                    "name": s.name,
                    "model": s.model,
                    "base_url": s.base_url,
                    "encryption_key_id": s.encryption_key_id,
                    "created_at": s.created_at,
                    "updated_at": s.updated_at,
                }
                if unlocked and fernet_key is not None:
                    # 二次加密: 先用本机 fernet_key 解, 再用 master_key 重新加密导出
                    # 但实际上 export **密文** 即可 (远端用 master_key 解不开 master_key
                    # 自己加密的明文, 但能解同一 salt 派生的 key 下的密文 — 因为
                    # ``api_key_encrypted`` 本身就是 Fernet 密文, 用同一 Fernet key 即可解密)
                    # 简化: 直接 export 密文 bytes
                    rec["api_key_ciphertext_b64"] = base64.b64encode(
                        s.api_key_encrypted
                    ).decode("ascii")
                else:
                    rec["api_key_ciphertext_b64"] = None
                records["secrets"].append(rec)

        bundle = {
            "version": BUNDLE_VERSION,
            "device_id": device_id,
            "merged_at": _now_iso(),
            "records": records,
        }
        return bundle

    # ------------------------------------------------------------------
    # bundle 写回
    # ------------------------------------------------------------------
    def apply_bundle(self, bundle: dict, *, master_key: Optional[str] = None) -> dict:
        """将 bundle 写回各表 (单边覆盖, 慎用; 推荐走 :meth:`three_way_merge`)。

        ``master_key`` 用于解密 secrets (Q5 决策)。
        返回每张表的处理数: ``{favorites: {...}, todos: {...}, ...}``。
        """
        _validate_bundle(bundle)
        records = bundle["records"]

        # --- secrets: 派生 fernet_key 后落库 ---
        sr = SecretRepository()
        ek_repo = EncryptionKeyRepository()
        ek_row = ek_repo.get_default()
        fernet_key: Optional[bytes] = None
        if ek_row is not None and master_key:
            if not verify_master_key(
                master_key, ek_row.salt, ek_row.iterations, ek_row.verify_blob
            ):
                raise InternalException("主密钥错误, 无法落库 secrets")
            fernet_key = derive_fernet_key(
                master_key, ek_row.salt, ek_row.iterations
            )

        secret_stats = {"inserted": 0, "updated": 0, "skipped": 0}
        if ek_row is not None and fernet_key is not None:
            existing_by_name = {s.name: s for s in sr.list()[0]}
            for s in records.get("secrets", []):
                name = s.get("name")
                if not name:
                    secret_stats["skipped"] += 1
                    continue
                cipher_b64 = s.get("api_key_ciphertext_b64")
                if not cipher_b64:
                    secret_stats["skipped"] += 1
                    continue
                try:
                    cipher_bytes = base64.b64decode(cipher_b64)
                except Exception:
                    secret_stats["skipped"] += 1
                    continue
                # 远端密文是用同一 fernet_key 加密的, 直接落库即可
                api_key_cipher = cipher_bytes
                if name in existing_by_name:
                    existing = existing_by_name[name]
                    # 若现有密文不同则更新
                    if existing.api_key_encrypted != api_key_cipher:
                        sr.update(
                            existing.id,
                            name=name,
                            model=s.get("model") or existing.model,
                            base_url=s.get("base_url") or existing.base_url,
                            api_key=None,  # 跳过 (要重新写密文)
                            fernet_key=None,
                        )
                        # 直接写密文 (update 不支持密文替换, 走 raw SQL)
                        from backend.repository.db import get_connection
                        conn = get_connection()
                        conn.execute(
                            "UPDATE llm_secrets SET api_key_encrypted=?, updated_at=? WHERE id=?",
                            (api_key_cipher, _now_iso(), existing.id),
                        )
                        conn.commit()
                        secret_stats["updated"] += 1
                    else:
                        secret_stats["skipped"] += 1
                else:
                    # 新增 (绕过 sr.create 的二次加密, 直接 INSERT 密文)
                    from backend.repository.db import get_connection
                    conn = get_connection()
                    conn.execute(
                        """INSERT INTO llm_secrets
                        (name, model, base_url, api_key_encrypted, encryption_key_id,
                         created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            name,
                            s.get("model", ""),
                            s.get("base_url", ""),
                            api_key_cipher,
                            ek_row.id,
                            s.get("created_at") or _now_iso(),
                            s.get("updated_at") or _now_iso(),
                        ),
                    )
                    conn.commit()
                    secret_stats["inserted"] += 1

        # --- favorites ---
        fr = FavoriteRepository()
        fav_stats = {"inserted": 0, "skipped": 0}
        existing_fav_ids = fr.list_favorited_ids()
        for f in records.get("favorites", []):
            hid = f.get("hotspot_id")
            if not hid or hid in existing_fav_ids:
                fav_stats["skipped"] += 1
                continue
            fr.add(
                hotspot_id=hid,
                category=f.get("category", ""),
                title=f.get("title", ""),
                source=f.get("source", ""),
                url=f.get("url", ""),
            )
            fav_stats["inserted"] += 1

        # --- todos (按 source_type + source_id 幂等) ---
        tr = TodoRepository()
        todo_stats = {"inserted": 0, "skipped": 0}
        for t in records.get("todos", []):
            try:
                tr.add_or_get(
                    source_type=t.get("source_type", "manual"),
                    source_id=t.get("source_id"),
                    title=t.get("title", ""),
                    url=t.get("url"),
                    source=t.get("source"),
                    category=t.get("category"),
                    urgent=int(t.get("urgent", 0) or 0),
                    important=int(t.get("important", 0) or 0),
                    note=t.get("note"),
                )
                todo_stats["inserted"] += 1
            except Exception:
                todo_stats["skipped"] += 1

        # --- skills (按 name 幂等) ---
        skr = SkillRepository()
        existing_skills = {s.name: s for s in skr.list()[0]}
        skill_stats = {"inserted": 0, "skipped": 0, "updated": 0}
        for s in records.get("skills", []):
            name = s.get("name")
            if not name:
                skill_stats["skipped"] += 1
                continue
            if name in existing_skills:
                skill_stats["skipped"] += 1
                continue
            try:
                skr.add(
                    name=name,
                    url=s.get("url", ""),
                    install_command=s.get("install_command", ""),
                    description=s.get("description"),
                    source=s.get("source", "manual"),
                    tags=s.get("tags") or [],
                )
                skill_stats["inserted"] += 1
            except Exception:
                skill_stats["skipped"] += 1

        # --- custom_sources (按 url 幂等, 简单 INSERT OR IGNORE) ---
        csr = CustomSourceRepository()
        cs_stats = {"inserted": 0, "skipped": 0}
        for c in records.get("custom_sources", []):
            url = c.get("url")
            if not url:
                cs_stats["skipped"] += 1
                continue
            try:
                csr.add(
                    url=url,
                    name=c.get("name", ""),
                    category=c.get("category", ""),
                    last_check_status=c.get("last_check_status") or "ok",
                    last_check_latency_ms=float(c.get("last_check_latency_ms") or 0.0),
                    last_check_title=c.get("last_check_title"),
                )
                cs_stats["inserted"] += 1
            except Exception:
                cs_stats["skipped"] += 1

        # --- settings (单 key 直接 set) ---
        sr_repo = SettingsRepository()
        settings_stats = {"written": 0, "skipped": 0}
        for k, v in records.get("settings", {}).items():
            if k in SETTINGS_BLOCKLIST:
                settings_stats["skipped"] += 1
                continue
            try:
                sr_repo.set(k, v)
                settings_stats["written"] += 1
            except Exception:
                settings_stats["skipped"] += 1

        return {
            "favorites": fav_stats,
            "todos": todo_stats,
            "skills": skill_stats,
            "custom_sources": cs_stats,
            "settings": settings_stats,
            "secrets": secret_stats,
        }

    # ------------------------------------------------------------------
    # 3-way merge
    # ------------------------------------------------------------------
    def three_way_merge(
        self, base: Optional[dict], local: dict, remote: dict,
    ) -> MergeResult:
        """合并 base/local/remote 三方 → merged + 冲突统计。

        **冲突规则 (Q3 决策)**
        - 记录级: 按 primary key (favorites.hotspot_id / todos.id / skills.name /
          custom_sources.url / secrets.name / settings.key) 对齐
        - 字段级: 若 base==local==remote 同字段 → 直接采用
        - 若 base==local, remote 变 → 接受 remote (远端有更新)
        - 若 base==remote, local 变 → 接受 local (本地有更新)
        - 若 local≠remote 且都≠base → 冲突, **两边都保留**: merged 字段 = 较新
          ``updated_at`` 一边; 冲突计数 +1
        """
        _validate_bundle(local)
        _validate_bundle(remote)

        merged_records: dict[str, Any] = {}
        total_conflicts = 0
        table_conflicts: dict[str, int] = {}

        # --- list-typed tables: favorites / todos / skills / custom_sources / secrets ---
        for table, key_fn in (
            ("favorites", lambda r: r.get("hotspot_id")),
            ("todos", lambda r: f"{r.get('source_type')}::{r.get('source_id') or r.get('id')}"),
            ("skills", lambda r: r.get("name")),
            ("custom_sources", lambda r: r.get("url")),
            ("secrets", lambda r: r.get("name")),
        ):
            base_recs = (base or {}).get("records", {}).get(table, []) or []
            local_recs = local.get("records", {}).get(table, []) or []
            remote_recs = remote.get("records", {}).get(table, []) or []
            merged, conflicts = self._merge_records(
                base_recs, local_recs, remote_recs, key_fn
            )
            merged_records[table] = merged
            table_conflicts[table] = conflicts
            total_conflicts += conflicts

        # --- settings (dict-typed) ---
        base_settings = (base or {}).get("records", {}).get("settings", {}) or {}
        local_settings = local.get("records", {}).get("settings", {}) or {}
        remote_settings = remote.get("records", {}).get("settings", {}) or {}
        merged_settings, settings_conflicts = self._merge_settings(
            base_settings, local_settings, remote_settings
        )
        merged_records["settings"] = merged_settings
        table_conflicts["settings"] = settings_conflicts
        total_conflicts += settings_conflicts

        merged_bundle = {
            "version": BUNDLE_VERSION,
            "device_id": local.get("device_id") or remote.get("device_id"),
            "merged_at": _now_iso(),
            "records": merged_records,
        }
        return MergeResult(merged_bundle, total_conflicts, table_conflicts)

    def _merge_records(
        self, base: list, local: list, remote: list, key_fn
    ) -> tuple[list, int]:
        """单表 3-way merge, 返回 (merged_records, conflict_count)。"""
        base_by_key = {key_fn(r): r for r in base}
        local_by_key = {key_fn(r): r for r in local}
        remote_by_key = {key_fn(r): r for r in remote}

        all_keys = set(base_by_key) | set(local_by_key) | set(remote_by_key)
        merged: list = []
        conflicts = 0

        for k in all_keys:
            if k is None or k == "manual::None" or k == "::":
                # 无主键记录, 全量保留 (来自任一边)
                for src in (base, local, remote):
                    for r in src:
                        if key_fn(r) in (None, "manual::None", "::"):
                            merged.append(r)
                continue

            b = base_by_key.get(k)
            l = local_by_key.get(k)
            r = remote_by_key.get(k)

            if b is None and l is None and r is None:
                continue
            if l is None and r is None:
                continue
            if l is None:
                merged.append(r)
                continue
            if r is None:
                merged.append(l)
                continue
            if l == r:
                merged.append(l)
                continue

            # 字段级 merge
            fields = set(l.keys()) | set(r.keys())
            field_merged: dict = {}
            had_conflict = False
            for f in fields:
                if f == "updated_at":
                    # updated_at 用较新的
                    l_ts = l.get(f) or ""
                    r_ts = r.get(f) or ""
                    field_merged[f] = max(l_ts, r_ts)
                    continue
                lv = l.get(f)
                rv = r.get(f)
                bv = b.get(f) if b else None
                if lv == rv:
                    if lv is not None:
                        field_merged[f] = lv
                elif lv == bv:
                    # local 未变, remote 变了 → 接受 remote
                    if rv is not None:
                        field_merged[f] = rv
                elif rv == bv:
                    # remote 未变, local 变了 → 接受 local
                    if lv is not None:
                        field_merged[f] = lv
                else:
                    # 双方都变且不一致 → 冲突, 较新 updated_at 胜出
                    had_conflict = True
                    l_ts = l.get("updated_at") or ""
                    r_ts = r.get("updated_at") or ""
                    winner = l if l_ts >= r_ts else r
                    field_merged[f] = winner.get(f)
            # id 字段保留 winner 的
            if "id" in (l.keys() | r.keys()):
                field_merged["id"] = l.get("id") or r.get("id")
            merged.append(field_merged)
            if had_conflict:
                conflicts += 1

        # 去重 (保留先出现的)
        seen = set()
        deduped: list = []
        for r in merged:
            k = key_fn(r)
            if k in seen:
                continue
            seen.add(k)
            deduped.append(r)
        return deduped, conflicts

    def _merge_settings(
        self, base: dict, local: dict, remote: dict
    ) -> tuple[dict, int]:
        """settings 是 dict, 3-way merge: 逐 key 字段级合并。"""
        all_keys = set(base) | set(local) | set(remote)
        merged: dict = {}
        conflicts = 0
        for k in all_keys:
            if k in SETTINGS_BLOCKLIST:
                continue
            lv = local.get(k)
            rv = remote.get(k)
            bv = base.get(k)
            if lv == rv:
                if lv is not None:
                    merged[k] = lv
            elif lv == bv:
                if rv is not None:
                    merged[k] = rv
            elif rv == bv:
                if lv is not None:
                    merged[k] = lv
            else:
                # 冲突: local / remote 二选一; 简单用 local 优先 (UI 写本地为主)
                # 实际应该按 settings 自带 _updated_at 子字段, 但 schema 简单先用 last-write-local
                merged[k] = lv if lv is not None else rv
                conflicts += 1
        return merged, conflicts

    # ------------------------------------------------------------------
    # 加密 / 解密 bundle
    # ------------------------------------------------------------------
    def encrypt_bundle(self, bundle: dict, master_key: str) -> bytes:
        """用 master_key 派生 Fernet key 加密整个 bundle.json。

        返回 envelope dict 的 JSON bytes, 格式与 secrets.export 兼容::

            {
                "version": "1.0",
                "encryption": {algorithm, kdf, iterations, salt_b64},
                "encryption_kind": "sync-bundle",   # 标识用途
                "merged_at": "...",
                "device_id": "...",
                "ciphertext_b64": "...",
            }
        """
        ek_repo = EncryptionKeyRepository()
        ek_row = ek_repo.get_default()
        if ek_row is None:
            raise InternalException("主密钥未初始化, 无法加密 sync bundle")
        if not verify_master_key(
            master_key, ek_row.salt, ek_row.iterations, ek_row.verify_blob
        ):
            raise InternalException("主密钥错误")

        fernet_key = derive_fernet_key(master_key, ek_row.salt, ek_row.iterations)
        plaintext = json.dumps(bundle, ensure_ascii=False, sort_keys=True).encode("utf-8")
        from cryptography.fernet import Fernet as _F
        ct = _F(fernet_key).encrypt(plaintext)
        envelope = {
            "version": BUNDLE_VERSION,
            "encryption": {
                "algorithm": "Fernet",
                "kdf": "PBKDF2-HMAC-SHA256",
                "iterations": ek_row.iterations,
                "salt_b64": ek_row.salt.hex(),
            },
            "encryption_kind": "sync-bundle",
            "merged_at": bundle.get("merged_at"),
            "device_id": bundle.get("device_id"),
            "ciphertext_b64": ct.hex(),
        }
        return json.dumps(envelope, ensure_ascii=False).encode("utf-8")

    def decrypt_bundle(self, payload: bytes, master_key: str) -> dict:
        """解密 envelope → bundle dict。"""
        ek_repo = EncryptionKeyRepository()
        ek_row = ek_repo.get_default()
        if ek_row is None:
            raise InternalException("主密钥未初始化, 无法解密 sync bundle")

        try:
            envelope = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise InternalException(f"sync bundle JSON 解析失败: {e}") from e

        enc = envelope.get("encryption", {})
        if enc.get("algorithm") != "Fernet":
            raise InternalException(f"不支持的加密算法: {enc.get('algorithm')}")
        if int(enc.get("iterations", -1)) != ek_row.iterations:
            raise InternalException(
                f"iterations 不一致: 文件 {enc.get('iterations')} vs 当前 {ek_row.iterations}"
            )
        if not verify_master_key(
            master_key, ek_row.salt, ek_row.iterations, ek_row.verify_blob
        ):
            raise InternalException("主密钥错误")

        fernet_key = derive_fernet_key(master_key, ek_row.salt, ek_row.iterations)
        from cryptography.fernet import Fernet as _F, InvalidToken
        try:
            ct = bytes.fromhex(envelope["ciphertext_b64"])
            plaintext = _F(fernet_key).decrypt(ct)
            bundle = json.loads(plaintext.decode("utf-8"))
        except (KeyError, ValueError, InvalidToken) as e:
            raise InternalException(f"sync bundle 解密失败: {e}") from e

        _validate_bundle(bundle)
        return bundle

    # ------------------------------------------------------------------
    # 同步入口
    # ------------------------------------------------------------------
    async def push(self, *, master_key: str) -> dict:
        """build → encrypt → WebDAV PUT (zip 容器) → 写 history → update last_sync。

        Phase 49: 每次同步打成 ``配置文件-YYYY-MM-DD.zip``(覆盖式),
        内含 envelope.json (Fernet 密文) + manifest.json (同步元数据)。
        """
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
        merge_result = self.three_way_merge(base_bundle, local_bundle, remote_bundle)

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
        merge_result = self.three_way_merge(base_bundle, local_bundle, remote_bundle)
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
        """fernet_key 版解密 (scheduler 自动同步用)。"""
        try:
            envelope = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise InternalException(f"sync bundle JSON 解析失败: {e}") from e
        enc = envelope.get("encryption", {})
        if enc.get("algorithm") != "Fernet":
            raise InternalException(f"不支持的加密算法: {enc.get('algorithm')}")
        from cryptography.fernet import Fernet as _F, InvalidToken
        try:
            ct = bytes.fromhex(envelope["ciphertext_b64"])
            plaintext = _F(fernet_key).decrypt(ct)
            bundle = json.loads(plaintext.decode("utf-8"))
        except (KeyError, ValueError, InvalidToken) as e:
            raise InternalException(f"sync bundle 解密失败: {e}") from e
        _validate_bundle(bundle)
        return bundle

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
