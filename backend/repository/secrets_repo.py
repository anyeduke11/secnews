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
from typing import Optional

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
    api_key_encrypted: bytes
    encryption_key_id: int
    created_at: str
    updated_at: str

    def to_dict(self, *, reveal: Optional[str] = None) -> dict:
        """默认隐藏 api_key; reveal 明文 (已 unlock 时) 才填。"""
        return {
            "id": self.id,
            "name": self.name,
            "model": self.model,
            "base_url": self.base_url,
            "api_key_masked": "•" * 8,
            "api_key": reveal,  # 显式传 None 时前端拿不到
            "encryption_key_id": self.encryption_key_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(row: sqlite3.Row) -> SecretItem:
    return SecretItem(
        id=int(row["id"]),
        name=str(row["name"]),
        model=str(row["model"]),
        base_url=str(row["base_url"]),
        api_key_encrypted=row["api_key_encrypted"],
        encryption_key_id=int(row["encryption_key_id"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


class SecretRepository:
    def list(self) -> tuple[list[SecretItem], int]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM llm_secrets ORDER BY created_at DESC"
        ).fetchall()
        return [_row(r) for r in rows], len(rows)

    def get(self, secret_id: int) -> Optional[SecretItem]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM llm_secrets WHERE id = ?", (int(secret_id),)
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
    ) -> SecretItem:
        if not name or not name.strip():
            raise InternalException("name 不能为空")
        if not model or not model.strip():
            raise InternalException("model 不能为空")
        if not base_url or not base_url.strip():
            raise InternalException("base_url 不能为空")
        if not api_key or not api_key.strip():
            raise InternalException("api_key 不能为空")

        cipher = encrypt_api_key(fernet_key, api_key.strip())
        conn = get_connection()
        now = _now_iso()
        try:
            conn.execute("BEGIN")
            cur = conn.execute(
                """
                INSERT INTO llm_secrets (
                    name, model, base_url, api_key_encrypted,
                    encryption_key_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name.strip(),
                    model.strip(),
                    base_url.strip(),
                    cipher,
                    int(encryption_key_id),
                    now,
                    now,
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
            api_key_encrypted=cipher,
            encryption_key_id=int(encryption_key_id),
            created_at=now,
            updated_at=now,
        )

    def update(
        self,
        secret_id: int,
        *,
        name: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        fernet_key: Optional[bytes] = None,
    ) -> SecretItem:
        existing = self.get(secret_id)
        if existing is None:
            raise InternalException(f"secret {secret_id} 不存在")

        new_name = name.strip() if name is not None else existing.name
        new_model = model.strip() if model is not None else existing.model
        new_url = base_url.strip() if base_url is not None else existing.base_url

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
                    name = ?, model = ?, base_url = ?,
                    api_key_encrypted = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_name, new_model, new_url, new_cipher, now, int(secret_id)),
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


__all__ = ["SecretRepository", "SecretItem"]
