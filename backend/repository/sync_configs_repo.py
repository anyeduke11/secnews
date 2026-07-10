"""Phase 42 sync_configs 仓库: WebDAV 同步配置 (单实例)。"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.db import get_connection


@dataclass
class SyncConfigRow:
    id: int
    name: str
    webdav_url: Optional[str]
    webdav_username: Optional[str]
    webdav_password_encrypted: Optional[bytes]
    webdav_password_salt: Optional[bytes]
    webdav_password_iters: int
    remote_path: str
    auto_sync_enabled: bool
    auto_sync_interval_minutes: int
    sync_frequency: str
    last_sync_at: Optional[str]
    last_sync_status: Optional[str]
    last_sync_error: Optional[str]
    last_sync_direction: Optional[str]
    device_id: Optional[str]
    created_at: str
    updated_at: str

    def to_dict(self, *, include_secrets: bool = False) -> dict:
        d = {
            "id": self.id,
            "name": self.name,
            "webdav_url": self.webdav_url,
            "webdav_username": self.webdav_username,
            "remote_path": self.remote_path,
            "auto_sync_enabled": bool(self.auto_sync_enabled),
            "auto_sync_interval_minutes": self.auto_sync_interval_minutes,
            "sync_frequency": self.sync_frequency,
            "last_sync_at": self.last_sync_at,
            "last_sync_status": self.last_sync_status,
            "last_sync_error": self.last_sync_error,
            "last_sync_direction": self.last_sync_direction,
            "device_id": self.device_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "has_password": self.webdav_password_encrypted is not None,
        }
        return d


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(r: sqlite3.Row) -> SyncConfigRow:
    return SyncConfigRow(
        id=int(r["id"]),
        name=str(r["name"]),
        webdav_url=(str(r["webdav_url"]) if r["webdav_url"] is not None else None),
        webdav_username=(str(r["webdav_username"]) if r["webdav_username"] is not None else None),
        webdav_password_encrypted=r["webdav_password_encrypted"],
        webdav_password_salt=r["webdav_password_salt"],
        webdav_password_iters=int(r["webdav_password_iters"]),
        remote_path=str(r["remote_path"]),
        auto_sync_enabled=bool(int(r["auto_sync_enabled"])),
        auto_sync_interval_minutes=int(r["auto_sync_interval_minutes"]),
        sync_frequency=(str(r["sync_frequency"]) if r["sync_frequency"] is not None else "weekly"),
        last_sync_at=(str(r["last_sync_at"]) if r["last_sync_at"] is not None else None),
        last_sync_status=(str(r["last_sync_status"]) if r["last_sync_status"] is not None else None),
        last_sync_error=(str(r["last_sync_error"]) if r["last_sync_error"] is not None else None),
        last_sync_direction=(str(r["last_sync_direction"]) if r["last_sync_direction"] is not None else None),
        device_id=(str(r["device_id"]) if r["device_id"] is not None else None),
        created_at=str(r["created_at"]),
        updated_at=str(r["updated_at"]),
    )


class SyncConfigRepository:
    """sync_configs 表 CRUD (单实例)。"""

    DEFAULT_NAME = "default"

    # ------------------------------------------------------------------
    def get_default(self) -> Optional[SyncConfigRow]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM sync_configs WHERE name = ? LIMIT 1",
            (self.DEFAULT_NAME,),
        ).fetchone()
        return _row(row) if row else None

    def get_by_id(self, cid: int) -> Optional[SyncConfigRow]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM sync_configs WHERE id = ?", (int(cid),)
        ).fetchone()
        return _row(row) if row else None

    # ------------------------------------------------------------------
    def upsert(
        self,
        *,
        webdav_url: Optional[str] = None,
        webdav_username: Optional[str] = None,
        webdav_password_encrypted: Optional[bytes] = None,
        webdav_password_salt: Optional[bytes] = None,
        webdav_password_iters: int = 600000,
        remote_path: str = "/hotspot/config.json",
        auto_sync_enabled: bool = False,
        auto_sync_interval_minutes: int = 10080,
        sync_frequency: str = "weekly",
        device_id: Optional[str] = None,
    ) -> SyncConfigRow:
        """upsert 默认实例; 不存在则 create, 存在则 update (部分字段)。"""
        conn = get_connection()
        now = _now_iso()
        existing = self.get_default()
        try:
            conn.execute("BEGIN")
            if existing is None:
                cur = conn.execute(
                    """
                    INSERT INTO sync_configs (
                        name, webdav_url, webdav_username,
                        webdav_password_encrypted, webdav_password_salt,
                        webdav_password_iters, remote_path,
                        auto_sync_enabled, auto_sync_interval_minutes,
                        sync_frequency, device_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.DEFAULT_NAME,
                        webdav_url,
                        webdav_username,
                        webdav_password_encrypted,
                        webdav_password_salt,
                        webdav_password_iters,
                        remote_path,
                        1 if auto_sync_enabled else 0,
                        auto_sync_interval_minutes,
                        sync_frequency,
                        device_id,
                        now,
                        now,
                    ),
                )
                new_id = int(cur.lastrowid)
            else:
                new_url = webdav_url if webdav_url is not None else existing.webdav_url
                new_user = webdav_username if webdav_username is not None else existing.webdav_username
                new_pwd = webdav_password_encrypted if webdav_password_encrypted is not None else existing.webdav_password_encrypted
                new_salt = webdav_password_salt if webdav_password_salt is not None else existing.webdav_password_salt
                new_device = device_id if device_id is not None else existing.device_id
                new_freq = sync_frequency if sync_frequency is not None else existing.sync_frequency

                conn.execute(
                    """
                    UPDATE sync_configs SET
                        webdav_url = ?,
                        webdav_username = ?,
                        webdav_password_encrypted = ?,
                        webdav_password_salt = ?,
                        webdav_password_iters = ?,
                        remote_path = ?,
                        auto_sync_enabled = ?,
                        auto_sync_interval_minutes = ?,
                        sync_frequency = ?,
                        device_id = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        new_url,
                        new_user,
                        new_pwd,
                        new_salt,
                        webdav_password_iters,
                        remote_path,
                        1 if auto_sync_enabled else 0,
                        auto_sync_interval_minutes,
                        new_freq,
                        new_device,
                        now,
                        int(existing.id),
                    ),
                )
                new_id = int(existing.id)
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error("sync_config upsert failed", extra={"err": str(e)})
            raise InternalException(f"sync_config upsert failed: {e}") from e

        out = self.get_by_id(new_id)
        if out is None:
            raise InternalException("sync_config disappeared after upsert")
        return out

    def update_device_id(self, cid: int, device_id: str) -> None:
        """单独更新 device_id (启动时如果缺失就补一个)。"""
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE sync_configs SET device_id=?, updated_at=? WHERE id=?",
                (device_id, _now_iso(), int(cid)),
            )
        except Exception as e:
            logger.error("update_device_id failed", extra={"err": str(e)})
            raise InternalException(f"update_device_id failed: {e}") from e

    def update_last_sync(
        self,
        cid: int,
        *,
        at: str,
        status: str,
        error: Optional[str] = None,
        direction: Optional[str] = None,
    ) -> None:
        conn = get_connection()
        try:
            conn.execute(
                """
                UPDATE sync_configs SET
                    last_sync_at = ?,
                    last_sync_status = ?,
                    last_sync_error = ?,
                    last_sync_direction = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (at, status, error, direction, _now_iso(), int(cid)),
            )
        except Exception as e:
            logger.error("update_last_sync failed", extra={"err": str(e)})
            raise InternalException(f"update_last_sync failed: {e}") from e

    def delete(self, cid: int) -> bool:
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            cur = conn.execute("DELETE FROM sync_configs WHERE id = ?", (int(cid),))
            n = int(cur.rowcount)
            conn.execute("COMMIT")
            return n > 0
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error("sync_config delete failed", extra={"err": str(e)})
            raise InternalException(f"sync_config delete failed: {e}") from e

    def delete_all(self) -> int:
        """清空所有 sync_configs (admin reset 用, 因为 webdav password 加密依赖 master_key)。"""
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            cur = conn.execute("DELETE FROM sync_configs")
            conn.execute("COMMIT")
            return int(cur.rowcount)
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error("sync_config delete_all failed", extra={"err": str(e)})
            raise InternalException(f"sync_config delete_all failed: {e}") from e


__all__ = ["SyncConfigRepository", "SyncConfigRow"]
