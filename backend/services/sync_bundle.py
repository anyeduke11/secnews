"""Sync bundle serialization — build, encrypt, decrypt, apply.

This module handles the bundle lifecycle:
- :func:`build_bundle` — read local config → bundle dict
- :func:`apply_bundle` — bundle dict → write back to all tables
- :func:`encrypt_bundle` / :func:`decrypt_bundle` — Fernet encrypt/decrypt with master_key
- :func:`decrypt_bundle_with_fernet_key` — Fernet decrypt with pre-derived key
"""

from __future__ import annotations

import base64
import json
from typing import Any, Optional

from backend.crypto import (
    derive_fernet_key,
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
from backend.repository.todo_repo import TodoRepository
from backend.services.sync_merge import (
    BUNDLE_VERSION,
    SETTINGS_BLOCKLIST,
    _now_iso,
    validate_bundle,
)


# -- secrets 元数据字段 (用于 3-way merge 比对, 不含加密密文) --
SECRET_MERGE_FIELDS = (
    "name", "model", "base_url", "updated_at",
)


def _read_cg_projects_for_sync() -> list[dict]:
    """读取 cg_projects 主表数据用于跨端同步 (不含 stages/links/activities)。

    Phase 2a: 仅同步主表, 子表 (stages/links/activities) 不跨端。
    """
    try:
        from backend.repository.codegarden_repo import CodegardenProjectRepository
        items, _ = CodegardenProjectRepository().list(
            include_archived=True, limit=1000
        )
        return items
    except Exception as e:
        logger.warning(f"_read_cg_projects_for_sync failed (skipped): {e}")
        return []


def _apply_cg_projects(items: list[dict]) -> int:
    """将 bundle 中的 codegarden_projects 写回 SQLite (upsert by id)。

    Phase 2a: 子表 (stages/links/activities) 不在 sync_bundle 内, 不处理。
    """
    if not items:
        return 0
    from backend.repository.db import get_connection
    conn = get_connection()
    n = 0
    for it in items:
        try:
            conn.execute(
                """
                INSERT INTO cg_projects (
                    id, name, display_name, description, type, source_type,
                    lifecycle_stage, health_score, local_path, repo_url,
                    upstream_url, upstream_default_branch, commits_behind,
                    commits_ahead, last_synced_at, source_item_id,
                    source_type_detail, tags, tech_stack, domain, priority,
                    active_skill_ids, created_at, last_activity_at, archived_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name, display_name=excluded.display_name,
                    description=excluded.description, type=excluded.type,
                    source_type=excluded.source_type,
                    lifecycle_stage=excluded.lifecycle_stage,
                    health_score=excluded.health_score, local_path=excluded.local_path,
                    repo_url=excluded.repo_url, upstream_url=excluded.upstream_url,
                    upstream_default_branch=excluded.upstream_default_branch,
                    commits_behind=excluded.commits_behind,
                    commits_ahead=excluded.commits_ahead,
                    last_synced_at=excluded.last_synced_at,
                    source_item_id=excluded.source_item_id,
                    source_type_detail=excluded.source_type_detail,
                    tags=excluded.tags, tech_stack=excluded.tech_stack,
                    domain=excluded.domain, priority=excluded.priority,
                    active_skill_ids=excluded.active_skill_ids,
                    last_activity_at=excluded.last_activity_at,
                    archived_at=excluded.archived_at
                """,
                (
                    it["id"], it["name"], it.get("display_name"),
                    it.get("description"), it["type"], it["source_type"],
                    it["lifecycle_stage"], it.get("health_score", 0),
                    it.get("local_path"), it.get("repo_url"),
                    it.get("upstream_url"), it.get("upstream_default_branch"),
                    it.get("commits_behind", 0), it.get("commits_ahead", 0),
                    it.get("last_synced_at"), it.get("source_item_id"),
                    it.get("source_type_detail"),
                    it.get("tags", "[]"), it.get("tech_stack", "[]"),
                    it.get("domain"), it.get("priority", 0),
                    it.get("active_skill_ids", "[]"),
                    it["created_at"], it.get("last_activity_at"),
                    it.get("archived_at"),
                ),
            )
            n += 1
        except Exception as e:
            logger.warning(f"_apply_cg_projects upsert {it.get('id')} failed: {e}")
    return n


def _read_cg_services_for_sync() -> list[dict]:
    """读取 cg_services 主表数据用于跨端同步.

    Phase 2b 决策: 仅 cg_services 跨端同步 (含 env_vars 加密字段).
    cg_resources / cg_dependencies / cg_events 不跨端 (设备本地状态).
    """
    try:
        from backend.repository.codegarden_service_repo import CodegardenServiceRepository
        items, _ = CodegardenServiceRepository().list(limit=1000)
        return items
    except Exception as e:
        logger.warning(f"_read_cg_services_for_sync failed (skipped): {e}")
        return []


def _apply_cg_services(items: list[dict]) -> int:
    """将 bundle 中的 codegarden_services 写回 SQLite (upsert by id).

    Phase 2b: env_vars 字段已用 Fernet 加密, 跨端时密文直接同步 (需同 master_key).
    """
    if not items:
        return 0
    from backend.repository.db import get_connection
    conn = get_connection()
    n = 0
    for it in items:
        try:
            # dependencies / env_vars 在源端是 list/dict, 落库前转 JSON 字符串
            deps = it.get("dependencies")
            deps_json = (
                deps if isinstance(deps, str) else json.dumps(deps or [], ensure_ascii=False)
            )
            env = it.get("env_vars")
            env_json = (
                env if isinstance(env, str) else json.dumps(env or {}, ensure_ascii=False)
            )
            conn.execute(
                """
                INSERT INTO cg_services (
                    id, project_id, name, namespace, type, runtime, status,
                    endpoint_host, endpoint_port, endpoint_domain,
                    health_check_type, health_check_path, health_check_interval,
                    cpu_limit, memory_limit, dependencies, env_vars,
                    created_at, last_checked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    project_id=excluded.project_id, name=excluded.name,
                    namespace=excluded.namespace, type=excluded.type,
                    runtime=excluded.runtime, status=excluded.status,
                    endpoint_host=excluded.endpoint_host,
                    endpoint_port=excluded.endpoint_port,
                    endpoint_domain=excluded.endpoint_domain,
                    health_check_type=excluded.health_check_type,
                    health_check_path=excluded.health_check_path,
                    health_check_interval=excluded.health_check_interval,
                    cpu_limit=excluded.cpu_limit, memory_limit=excluded.memory_limit,
                    dependencies=excluded.dependencies, env_vars=excluded.env_vars,
                    last_checked_at=excluded.last_checked_at
                """,
                (
                    it["id"], it.get("project_id"), it["name"], it.get("namespace"),
                    it["type"], it["runtime"], it["status"],
                    it.get("endpoint_host"), it.get("endpoint_port"),
                    it.get("endpoint_domain"),
                    it.get("health_check_type"), it.get("health_check_path"),
                    int(it.get("health_check_interval") or 30),
                    it.get("cpu_limit"), it.get("memory_limit"),
                    deps_json, env_json,
                    it["created_at"], it.get("last_checked_at"),
                ),
            )
            n += 1
        except Exception as e:
            logger.warning(f"_apply_cg_services upsert {it.get('id')} failed: {e}")
    return n


# ---------------------------------------------------------------------------
# Bundle building
# ---------------------------------------------------------------------------
def build_bundle(*, device_id: Optional[str] = None) -> dict:
    """Read all local config → bundle dict.

    ``device_id`` not provided → use sync_configs.device_id (generates on first call).
    """
    from backend.repository.sync_configs_repo import SyncConfigRepository
    from backend.services.secrets_service import _is_unlocked, _unlock_state

    cfg = SyncConfigRepository().get_default()
    if device_id is None:
        if cfg is not None and cfg.device_id:
            device_id = cfg.device_id
        else:
            import uuid
            device_id = str(uuid.uuid4())
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
        "codegarden_projects": _read_cg_projects_for_sync(),
        "codegarden_services": _read_cg_services_for_sync(),  # Phase 2b
        "custom_sources": [
            src.to_dict() for src in CustomSourceRepository().list()
        ],
        "settings": {
            k: v for k, v in SettingsRepository().list_all().items()
            if k not in SETTINGS_BLOCKLIST
        },
        "secrets": [],
    }

    # secrets export (跨端时远端用同一 master_key 即可解密)
    ek = EncryptionKeyRepository()
    ek_row = ek.get_default()
    if ek_row is not None:
        if _is_unlocked(ek_row.id):
            fernet_key = _unlock_state[ek_row.id]["fernet_key"]
            unlocked = True
        else:
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
                rec["api_key_ciphertext_b64"] = base64.b64encode(
                    s.api_key_encrypted
                ).decode("ascii")
            else:
                rec["api_key_ciphertext_b64"] = None
            records["secrets"].append(rec)

    return {
        "version": BUNDLE_VERSION,
        "device_id": device_id,
        "merged_at": _now_iso(),
        "records": records,
    }


# ---------------------------------------------------------------------------
# Bundle apply (write back)
# ---------------------------------------------------------------------------
def apply_bundle(bundle: dict, *, master_key: Optional[str] = None) -> dict:
    """Write bundle records back to all tables.

    ``master_key`` is needed for decrypting secrets (Q5 decision).
    Returns per-table stats: {favorites: {...}, todos: {...}, ...}.
    """
    from backend.repository.db import get_connection
    from backend.crypto import decrypt_api_key

    validate_bundle(bundle)
    records = bundle["records"]

    # --- secrets ---
    sr = SecretRepository()
    ek_repo = EncryptionKeyRepository()
    ek_row = ek_repo.get_default()
    fernet_key: Optional[bytes] = None
    if ek_row is not None and master_key:
        if not verify_master_key(master_key, ek_row.salt, ek_row.iterations, ek_row.verify_blob):
            raise InternalException("主密钥错误, 无法落库 secrets")
        fernet_key = derive_fernet_key(master_key, ek_row.salt, ek_row.iterations)

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
            api_key_cipher = cipher_bytes
            if name in existing_by_name:
                existing = existing_by_name[name]
                if existing.api_key_encrypted != api_key_cipher:
                    sr.update(
                        existing.id, name=name, model=s.get("model") or existing.model,
                        base_url=s.get("base_url") or existing.base_url,
                        api_key=None, fernet_key=None,
                    )
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
                conn = get_connection()
                conn.execute(
                    """INSERT INTO llm_secrets (name, model, base_url, api_key_encrypted,
                        encryption_key_id, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (name, s.get("model", ""), s.get("base_url", ""),
                     api_key_cipher, ek_row.id,
                     s.get("created_at") or _now_iso(),
                     s.get("updated_at") or _now_iso()),
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
        fr.add(hotspot_id=hid, category=f.get("category", ""),
               title=f.get("title", ""), source=f.get("source", ""), url=f.get("url", ""))
        fav_stats["inserted"] += 1

    # --- todos ---
    tr = TodoRepository()
    todo_stats = {"inserted": 0, "skipped": 0}
    for t in records.get("todos", []):
        try:
            tr.add_or_get(
                source_type=t.get("source_type", "manual"),
                source_id=t.get("source_id"), title=t.get("title", ""),
                url=t.get("url"), source=t.get("source"), category=t.get("category"),
                urgent=int(t.get("urgent", 0) or 0), important=int(t.get("important", 0) or 0),
                note=t.get("note"),
            )
            todo_stats["inserted"] += 1
        except Exception:
            todo_stats["skipped"] += 1

    # --- skills ---
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
            skr.add(name=name, url=s.get("url", ""), install_command=s.get("install_command", ""),
                    description=s.get("description"), source=s.get("source", "manual"), tags=s.get("tags") or [])
            skill_stats["inserted"] += 1
        except Exception:
            skill_stats["skipped"] += 1

    # --- custom_sources ---
    csr = CustomSourceRepository()
    cs_stats = {"inserted": 0, "skipped": 0}
    for c in records.get("custom_sources", []):
        url = c.get("url")
        if not url:
            cs_stats["skipped"] += 1
            continue
        try:
            csr.add(url=url, name=c.get("name", ""), category=c.get("category", ""),
                    last_check_status=c.get("last_check_status") or "ok",
                    last_check_latency_ms=float(c.get("last_check_latency_ms") or 0.0),
                    last_check_title=c.get("last_check_title"))
            cs_stats["inserted"] += 1
        except Exception:
            cs_stats["skipped"] += 1

    # --- codegarden_projects (Phase 2a) ---
    cg_stats = {"upserted": _apply_cg_projects(records.get("codegarden_projects", []))}

    # --- codegarden_services (Phase 2b) ---
    cg_svc_stats = {"upserted": _apply_cg_services(records.get("codegarden_services", []))}

    # --- settings ---
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
        "favorites": fav_stats, "todos": todo_stats, "skills": skill_stats,
        "custom_sources": cs_stats, "settings": settings_stats, "secrets": secret_stats,
        "codegarden_projects": cg_stats,
        "codegarden_services": cg_svc_stats,  # Phase 2b
    }


# ---------------------------------------------------------------------------
# Bundle encryption / decryption
# ---------------------------------------------------------------------------
def encrypt_bundle(bundle: dict, master_key: str) -> bytes:
    """Encrypt entire bundle.json with Fernet using master_key-derived key.

    Returns envelope dict as JSON bytes:
        {version, encryption: {algorithm, kdf, iterations, salt_b64},
         encryption_kind, merged_at, device_id, ciphertext_b64}
    """
    from cryptography.fernet import Fernet as _F

    ek_repo = EncryptionKeyRepository()
    ek_row = ek_repo.get_default()
    if ek_row is None:
        raise InternalException("主密钥未初始化, 无法加密 sync bundle")
    if not verify_master_key(master_key, ek_row.salt, ek_row.iterations, ek_row.verify_blob):
        raise InternalException("主密钥错误")

    fernet_key = derive_fernet_key(master_key, ek_row.salt, ek_row.iterations)
    plaintext = json.dumps(bundle, ensure_ascii=False, sort_keys=True).encode("utf-8")
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


def decrypt_bundle(payload: bytes, master_key: str) -> dict:
    """Decrypt envelope → bundle dict."""
    from cryptography.fernet import Fernet as _F, InvalidToken

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
    if not verify_master_key(master_key, ek_row.salt, ek_row.iterations, ek_row.verify_blob):
        raise InternalException("主密钥错误")

    fernet_key = derive_fernet_key(master_key, ek_row.salt, ek_row.iterations)
    try:
        ct = bytes.fromhex(envelope["ciphertext_b64"])
        plaintext = _F(fernet_key).decrypt(ct)
        bundle = json.loads(plaintext.decode("utf-8"))
    except (KeyError, ValueError, InvalidToken) as e:
        raise InternalException(f"sync bundle 解密失败: {e}") from e

    validate_bundle(bundle)
    return bundle


def decrypt_bundle_with_fernet_key(payload: bytes, fernet_key: bytes) -> dict:
    """Decrypt bundle using a pre-derived fernet_key (scheduler auto-sync)."""
    from cryptography.fernet import Fernet as _F, InvalidToken

    try:
        envelope = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise InternalException(f"sync bundle JSON 解析失败: {e}") from e
    enc = envelope.get("encryption", {})
    if enc.get("algorithm") != "Fernet":
        raise InternalException(f"不支持的加密算法: {enc.get('algorithm')}")
    try:
        ct = bytes.fromhex(envelope["ciphertext_b64"])
        plaintext = _F(fernet_key).decrypt(ct)
        bundle = json.loads(plaintext.decode("utf-8"))
    except (KeyError, ValueError, InvalidToken) as e:
        raise InternalException(f"sync bundle 解密失败: {e}") from e
    validate_bundle(bundle)
    return bundle


def decode_remote_payload(raw: bytes) -> tuple[bytes, Optional[dict]]:
    """Unpack remote raw bytes → (envelope_bytes, manifest).

    Supports:
    - zip container (Phase 49+): envelope.json + manifest.json
    - raw json envelope (Phase 42 legacy): compatible read
    """
    from backend.services.sync_zip import extract_sync_zip

    if raw.startswith(b"PK"):  # ZIP magic number
        return extract_sync_zip(raw)
    # Otherwise treat as raw json envelope
    try:
        json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"既不是 zip 也不是合法 json: {e}") from e
    return raw, None


__all__ = [
    "build_bundle",
    "apply_bundle",
    "encrypt_bundle",
    "decrypt_bundle",
    "decrypt_bundle_with_fernet_key",
    "decode_remote_payload",
    "SECRET_MERGE_FIELDS",
]