"""Phase 41 加密主密钥表仓库: encryption_keys。

单实例模式: 整个 DB 只允许一行 (name='default')。
- 用 ``get_default()`` 读
- 用 ``setup_default()`` 写 (第二次调用直接抛错, 禁止重置)
- 用 ``is_setup()`` 检查是否已初始化
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from backend.crypto import DEFAULT_ITERATIONS, make_verify_blob, generate_salt
from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.db import get_connection


@dataclass
class EncryptionKeyRow:
    id: int
    name: str
    salt: bytes
    iterations: int
    verify_blob: bytes
    created_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "iterations": self.iterations,
            "created_at": self.created_at,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(row: sqlite3.Row) -> EncryptionKeyRow:
    return EncryptionKeyRow(
        id=int(row["id"]),
        name=str(row["name"]),
        salt=row["salt"],
        iterations=int(row["iterations"]),
        verify_blob=row["verify_blob"],
        created_at=str(row["created_at"]),
    )


class EncryptionKeyRepository:
    """encryption_keys 表的 CRUD (单实例)。"""

    DEFAULT_NAME = "default"

    # ------------------------------------------------------------------
    def is_setup(self) -> bool:
        conn = get_connection()
        row = conn.execute(
            "SELECT 1 AS x FROM encryption_keys WHERE name = ? LIMIT 1",
            (self.DEFAULT_NAME,),
        ).fetchone()
        return row is not None

    def get_default(self) -> Optional[EncryptionKeyRow]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM encryption_keys WHERE name = ? LIMIT 1",
            (self.DEFAULT_NAME,),
        ).fetchone()
        return _row(row) if row else None

    def get_by_id(self, key_id: int) -> Optional[EncryptionKeyRow]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM encryption_keys WHERE id = ? LIMIT 1",
            (int(key_id),),
        ).fetchone()
        return _row(row) if row else None

    # ------------------------------------------------------------------
    def setup_default(self, *, master_key: str) -> EncryptionKeyRow:
        """初始化主密钥 (全 DB 仅 1 次, 第二次调用抛错, 禁止重置)。

        Phase 41 决策: Q1 禁止重置 — 重复调用直接抛 InternalException。
        """
        if self.is_setup():
            raise InternalException(
                "主密钥已初始化; 按产品决策 (Q1) 禁止重置, 如需重置请删除数据库后重新初始化"
            )
        if not master_key or len(master_key) < 8:
            raise InternalException("主密钥长度必须 >= 8 字符")
        salt = generate_salt()
        iterations = DEFAULT_ITERATIONS
        verify_blob = make_verify_blob(master_key, salt, iterations)

        conn = get_connection()
        now = _now_iso()
        try:
            conn.execute("BEGIN")
            cur = conn.execute(
                """
                INSERT INTO encryption_keys (name, salt, iterations, verify_blob, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (self.DEFAULT_NAME, salt, iterations, verify_blob, now),
            )
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error("encryption_key setup failed", extra={"err": str(e)})
            raise InternalException(f"setup encryption_key failed: {e}") from e

        new_id = int(cur.lastrowid)
        return EncryptionKeyRow(
            id=new_id,
            name=self.DEFAULT_NAME,
            salt=salt,
            iterations=iterations,
            verify_blob=verify_blob,
            created_at=now,
        )

    # ------------------------------------------------------------------
    def delete_default(self) -> int:
        """删除主密钥行 (admin override, 需要在调用前用 confirm 字符串二次确认)。

        返回: 受影响行数 (0/1)。

        Phase 42 新增: Q1 决策"禁止重置"在产品上保持 (默认调用方不应触发),
        但 Phase 42 加入 ``/api/secrets/reset`` admin 端点, 走二次确认字符串
        后可强制清空。**使用后所有 llm_secrets 必须重新录入, 因旧 master_key
        派生的 Fernet key 无法解密新 master_key 派生的密文。**
        """
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            cur = conn.execute(
                "DELETE FROM encryption_keys WHERE name = ?",
                (self.DEFAULT_NAME,),
            )
            conn.execute("COMMIT")
            return int(cur.rowcount)
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error("delete_default failed", extra={"err": str(e)})
            raise InternalException(f"delete_default failed: {e}") from e


__all__ = ["EncryptionKeyRepository", "EncryptionKeyRow"]
