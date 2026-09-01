"""Phase 41 LLM 密钥仓库: llm_secrets CRUD。

要点
----
- 永远返回密文 (api_key_encrypted 字段), 明文只在 service 层 unlock 后拿到
- create / update 时强制要求 master_key (调用方传明文进来, repo 帮加密)
- 列表/详情不返回 api_key_encrypted 明文 (隐去 — 用空字符串代替)
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.crypto import encrypt_api_key
from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.db import get_connection


@dataclass
class SecretItem:
    id: int
    name: str
    model: str
    base_url: str
    provider: str
    api_key_encrypted: bytes
    encryption_key_id: int
    created_at: str
    updated_at: str
    owner_role: str = "admin"  # v0.7 Batch ⑨ B9-3: per-secret 权限位

    def to_dict(self, *, reveal: str | None = None) -> dict:
        """默认隐藏 api_key; reveal 明文 (已 unlock 时) 才填。"""
        return {
            "id": self.id,
            "name": self.name,
            "model": self.model,
            "base_url": self.base_url,
            "provider": self.provider,
            "api_key_masked": "•" * 8,
            "api_key": reveal,  # 显式传 None 时前端拿不到
            "encryption_key_id": self.encryption_key_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "owner_role": self.owner_role,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(row: sqlite3.Row) -> SecretItem:
    return SecretItem(
        id=int(row["id"]),
        name=str(row["name"]),
        model=str(row["model"]),
        base_url=str(row["base_url"]),
        provider=str(row["provider"]) if "provider" in row.keys() else "",
        api_key_encrypted=row["api_key_encrypted"],
        encryption_key_id=int(row["encryption_key_id"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        owner_role=str(row["owner_role"]) if "owner_role" in row.keys() and row["owner_role"] else "admin",
    )


# v0.7 Batch ⑨ B9-3: role 优先级 (高 → 低). actor_role >= owner_role 才能访问.
# admin 能看 admin + user 全部; user 只能看 user 自己的.
_ROLE_RANK = {"admin": 2, "user": 1}


def _role_can_access(actor_role: str, owner_role: str) -> bool:
    return _ROLE_RANK.get(actor_role, 0) >= _ROLE_RANK.get(owner_role, 0)


class SecretRepository:
    def list(self, actor_role: str = "admin") -> tuple[list[SecretItem], int]:
        """B9-3: actor_role 过滤. user 仅看 user-owned, admin 看全部."""
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM llm_secrets ORDER BY created_at DESC"
        ).fetchall()
        items = [
            _row(r) for r in rows
            if _role_can_access(actor_role, str(r["owner_role"]) if r["owner_role"] else "admin")
        ]
        return items, len(items)

    def get(self, secret_id: int, actor_role: str = "admin") -> SecretItem | None:
        """B9-3: 跨 role get 返 None (404 语义), 不抛异常 (避免暴露存在性)."""
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM llm_secrets WHERE id = ?", (int(secret_id),)
        ).fetchone()
        if not row:
            return None
        if not _role_can_access(actor_role, str(row["owner_role"]) if row["owner_role"] else "admin"):
            return None
        return _row(row)

    def get_by_provider(self, provider: str) -> SecretItem | None:
        """按 provider 拿一条 secret（多条时取 updated_at 最新）。

        AIService / LLMService 接入约定 — migration 074
        (``074_v0.6_llm_secrets_provider.sql``) 已下契约: 让 ai_hub
        能按 provider 名查表拿到明文。该 helper 是该契约的兑现点。

        复用 ``idx_llm_secrets_provider`` 索引（013_secrets.sql 建表时建立）。
        ``provider`` 留空字符串等价于未分类，等价于未命中 — 调用方应先做
        ``provider.strip()`` 非空判断。

        多条同 provider 按 ``updated_at DESC, id DESC`` 取最新 — 约定
        1 provider = 1 条有效 secret，重复录入时新覆盖旧。
        """
        if not provider or not provider.strip():
            return None
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM llm_secrets "
            "WHERE provider = ? "
            "ORDER BY updated_at DESC, id DESC LIMIT 1",
            (provider.strip(),),
        ).fetchone()
        return _row(row) if row else None

    def create(
        self,
        *,
        name: str,
        model: str,
        base_url: str,
        api_key: str,
        fernet_key: bytes,
        encryption_key_id: int,
        provider: str = "",
        owner_role: str = "admin",
    ) -> SecretItem:
        if not name or not name.strip():
            raise InternalException("name 不能为空")
        if not model or not model.strip():
            raise InternalException("model 不能为空")
        if not base_url or not base_url.strip():
            raise InternalException("base_url 不能为空")
        if not api_key or not api_key.strip():
            raise InternalException("api_key 不能为空")
        if owner_role not in ("admin", "user"):
            raise InternalException("owner_role 必须为 admin 或 user")

        cipher = encrypt_api_key(fernet_key, api_key.strip())
        conn = get_connection()
        now = _now_iso()
        try:
            conn.execute("BEGIN")
            cur = conn.execute(
                """
                INSERT INTO llm_secrets (
                    name, model, base_url, provider, api_key_encrypted,
                    encryption_key_id, created_at, updated_at, owner_role
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name.strip(),
                    model.strip(),
                    base_url.strip(),
                    (provider or "").strip(),
                    cipher,
                    int(encryption_key_id),
                    now,
                    now,
                    owner_role,
                ),
            )
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error("secret create failed", extra={"err": str(e)})
            raise InternalException(f"create secret failed: {e}") from e

        new_id = int(cur.lastrowid)
        return SecretItem(
            id=new_id,
            name=name.strip(),
            model=model.strip(),
            base_url=base_url.strip(),
            provider=(provider or "").strip(),
            api_key_encrypted=cipher,
            encryption_key_id=int(encryption_key_id),
            created_at=now,
            updated_at=now,
            owner_role=owner_role,
        )

    def update(
        self,
        secret_id: int,
        *,
        name: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        fernet_key: bytes | None = None,
        provider: str | None = None,
    ) -> SecretItem:
        existing = self.get(secret_id)
        if existing is None:
            raise InternalException(f"secret {secret_id} 不存在")

        new_name = name.strip() if name is not None else existing.name
        new_model = model.strip() if model is not None else existing.model
        new_url = base_url.strip() if base_url is not None else existing.base_url
        new_provider = (
            provider.strip() if provider is not None else existing.provider
        )

        if not new_name or not new_model or not new_url:
            raise InternalException("name/model/base_url 不能为空")

        if api_key is not None and api_key.strip() and fernet_key is not None:
            new_cipher = encrypt_api_key(fernet_key, api_key.strip())
        else:
            new_cipher = existing.api_key_encrypted

        conn = get_connection()
        now = _now_iso()
        try:
            conn.execute("BEGIN")
            conn.execute(
                """
                UPDATE llm_secrets SET
                    name = ?, model = ?, base_url = ?, provider = ?,
                    api_key_encrypted = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_name, new_model, new_url, new_provider, new_cipher, now, int(secret_id)),
            )
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error("secret update failed", extra={"err": str(e)})
            raise InternalException(f"update secret failed: {e}") from e

        updated = self.get(secret_id)
        if updated is None:
            raise InternalException(f"secret {secret_id} disappeared after update")
        return updated

    def delete(self, secret_id: int) -> bool:
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            cur = conn.execute(
                "DELETE FROM llm_secrets WHERE id = ?", (int(secret_id),)
            )
            n = int(cur.rowcount)
            conn.execute("COMMIT")
            return n > 0
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error("secret delete failed", extra={"err": str(e)})
            raise InternalException(f"delete secret failed: {e}") from e

    def delete_all(self) -> int:
        """清空所有 llm_secrets (admin reset 用)。

        Phase 42 新增: ``/api/secrets/reset`` 调用。返回受影响行数。
        """
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            cur = conn.execute("DELETE FROM llm_secrets")
            conn.execute("COMMIT")
            return int(cur.rowcount)
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error("secret delete_all failed", extra={"err": str(e)})
            raise InternalException(f"secret delete_all failed: {e}") from e

    def clear_access_logs(self) -> int:
        """清空 secret_access_logs (audit 痕迹一并清)。"""
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            cur = conn.execute("DELETE FROM secret_access_logs")
            conn.execute("COMMIT")
            return int(cur.rowcount)
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error("clear_access_logs failed", extra={"err": str(e)})
            raise InternalException(f"clear_access_logs failed: {e}") from e


__all__ = ["SecretItem", "SecretRepository"]
