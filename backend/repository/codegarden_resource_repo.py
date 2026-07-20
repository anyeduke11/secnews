"""Phase 2b CodeGarden 资源中枢 — cg_resources 表 CRUD + 端口分配/释放.

设计要点
--------
- 4 类资源: port / domain / env_template / volume, 用 type + value 识别
- port 资源 value 存端口号字符串 (TEXT, 与 schema 一致)
- hotspot 自身端口 8898 受保护, release_port 拒绝 (由 Service 层返回 403)
- find_free_port: 在 cg_resources 表中查找未分配端口 (8000-9999 范围)
- 实时端口占用 (lsof) 由 Service 层负责, repo 仅处理表内数据
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.db import get_connection


VALID_RESOURCE_TYPES = ("port", "domain", "env_template", "volume")
VALID_RESOURCE_STATUSES = ("allocated", "free", "reserved")

# 端口池范围 (与 spec §9.4 PortPool 视图一致)
PORT_RANGE_START = 8000
PORT_RANGE_END = 9999

# hotspot 自身受保护端口 (释放拒绝由 Service 层处理)
PROTECTED_PORTS = {8898}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def _parse_json(raw: Optional[str], default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw) if raw else default
    except (TypeError, ValueError):
        return default


# 延迟 import json 以避免顶部循环
import json  # noqa: E402


def _row_to_resource(row: sqlite3.Row) -> dict:
    return {
        "id": str(row["id"]),
        "type": str(row["type"]),
        "value": str(row["value"]),
        "status": str(row["status"]),
        "owner_service_id": row["owner_service_id"],
        "owner_project_id": row["owner_project_id"],
        "metadata": _parse_json(row["metadata"], {}),
        "reserved_until": row["reserved_until"],
        "created_at": str(row["created_at"]),
    }


class CodegardenResourceRepository:
    """cg_resources 表 CRUD + 按 type 筛选 + find_free_port + release_port."""

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    def create(
        self,
        *,
        type: str,
        value: str,
        status: str = "free",
        owner_service_id: Optional[str] = None,
        owner_project_id: Optional[str] = None,
        metadata: Optional[dict] = None,
        reserved_until: Optional[str] = None,
    ) -> dict:
        if type not in VALID_RESOURCE_TYPES:
            raise InternalException(
                f"type 必须为 {', '.join(VALID_RESOURCE_TYPES)}; got {type!r}"
            )
        if status not in VALID_RESOURCE_STATUSES:
            raise InternalException(
                f"status 必须为 {', '.join(VALID_RESOURCE_STATUSES)}; got {status!r}"
            )
        if not value or not str(value).strip():
            raise InternalException("value 不能为空")

        resource_id = _new_id()
        now = _now_iso()
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)

        conn = get_connection()
        try:
            conn.execute("BEGIN")
            conn.execute(
                """
                INSERT INTO cg_resources (
                    id, type, value, status, owner_service_id, owner_project_id,
                    metadata, reserved_until, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resource_id, type, str(value).strip(), status,
                    owner_service_id, owner_project_id, meta_json, reserved_until, now,
                ),
            )
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error(f"cg_resources create failed: {e}")
            raise InternalException(f"cg_resources create failed: {e}") from e

        return self.get(resource_id)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------
    def get(self, resource_id: str) -> Optional[dict]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM cg_resources WHERE id = ?", (resource_id,)
        ).fetchone()
        return _row_to_resource(row) if row else None

    def get_by_value(self, type: str, value: str) -> Optional[dict]:
        """按 (type, value) 查找资源 (如 port:8080)."""
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM cg_resources WHERE type = ? AND value = ?",
            (type, str(value)),
        ).fetchone()
        return _row_to_resource(row) if row else None

    def list(
        self,
        *,
        type: Optional[str] = None,
        status: Optional[str] = None,
        owner_service_id: Optional[str] = None,
        owner_project_id: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        conn = get_connection()
        where: list[str] = []
        params: list = []
        if type:
            where.append("type = ?")
            params.append(type)
        if status:
            where.append("status = ?")
            params.append(status)
        if owner_service_id:
            where.append("owner_service_id = ?")
            params.append(owner_service_id)
        if owner_project_id:
            where.append("owner_project_id = ?")
            params.append(owner_project_id)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        total_row = conn.execute(
            f"SELECT COUNT(*) AS n FROM cg_resources {where_sql}", params
        ).fetchone()
        total = int(total_row["n"]) if total_row else 0

        rows = conn.execute(
            f"""
            SELECT * FROM cg_resources {where_sql}
            ORDER BY created_at DESC, value ASC
            LIMIT ? OFFSET ?
            """,
            (*params, int(limit), int(offset)),
        ).fetchall()
        return [_row_to_resource(r) for r in rows], total

    # ------------------------------------------------------------------
    # 更新 / 删除
    # ------------------------------------------------------------------
    def update(self, resource_id: str, **fields) -> dict:
        existing = self.get(resource_id)
        if existing is None:
            raise InternalException(f"resource {resource_id} 不存在")

        allowed = {
            "status", "owner_service_id", "owner_project_id", "reserved_until",
        }
        json_fields = {"metadata"}

        sets: list[str] = []
        params: list = []
        for k, v in fields.items():
            if k is None:
                continue
            if k in allowed:
                sets.append(f"{k} = ?")
                params.append(v)
            elif k in json_fields:
                sets.append(f"{k} = ?")
                params.append(json.dumps(v, ensure_ascii=False))
            else:
                raise InternalException(f"不支持更新的字段: {k}")

        if not sets:
            return existing

        params.append(resource_id)

        conn = get_connection()
        try:
            conn.execute("BEGIN")
            conn.execute(
                f"UPDATE cg_resources SET {', '.join(sets)} WHERE id = ?",
                params,
            )
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise InternalException(f"cg_resources update failed: {e}") from e

        return self.get(resource_id)  # type: ignore[return-value]

    def delete(self, resource_id: str) -> bool:
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            cur = conn.execute(
                "DELETE FROM cg_resources WHERE id = ?", (resource_id,)
            )
            conn.execute("COMMIT")
            return cur.rowcount > 0
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise InternalException(f"cg_resources delete failed: {e}") from e

    # ------------------------------------------------------------------
    # 端口分配 / 释放
    # ------------------------------------------------------------------
    def find_free_port(
        self,
        *,
        exclude_ports: Optional[set[int]] = None,
        range_start: int = PORT_RANGE_START,
        range_end: int = PORT_RANGE_END,
    ) -> Optional[int]:
        """查找表内未分配的最小可用端口 (8000-9999 范围).

        Args:
            exclude_ports: 额外需排除的端口集合 (如 lsof 实时占用)
            range_start / range_end: 端口范围 (含)
        Returns:
            可用端口号, 或 None (范围已满)
        """
        exclude_ports = exclude_ports or set()
        exclude_ports |= PROTECTED_PORTS  # 永远排除受保护端口

        conn = get_connection()
        # 查询所有已分配/预留的端口
        rows = conn.execute(
            "SELECT value FROM cg_resources WHERE type = 'port' AND status IN ('allocated', 'reserved')"
        ).fetchall()
        allocated = {int(r["value"]) for r in rows if r["value"].isdigit()}

        for port in range(range_start, range_end + 1):
            if port in allocated or port in exclude_ports:
                continue
            return port
        return None

    def allocate_port(
        self,
        port: int,
        *,
        owner_service_id: Optional[str] = None,
        owner_project_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """分配指定端口: 如表内无记录则创建 allocated 记录; 如有 free 记录则更新为 allocated."""
        if port in PROTECTED_PORTS:
            raise InternalException(f"端口 {port} 受保护, 禁止分配 (hotspot 自身端口)")
        if not (PORT_RANGE_START <= port <= PORT_RANGE_END):
            raise InternalException(
                f"端口 {port} 超出允许范围 [{PORT_RANGE_START}, {PORT_RANGE_END}]"
            )

        existing = self.get_by_value("port", str(port))
        if existing is None:
            return self.create(
                type="port", value=str(port), status="allocated",
                owner_service_id=owner_service_id, owner_project_id=owner_project_id,
                metadata=metadata,
            )
        if existing["status"] == "allocated":
            raise InternalException(f"端口 {port} 已被分配")
        return self.update(existing["id"], status="allocated",
                           owner_service_id=owner_service_id,
                           owner_project_id=owner_project_id)

    def release_port(self, port: int) -> dict:
        """释放端口: status 改为 free, owner 清空. 受保护端口 (8898) 由 Service 层拒绝."""
        if port in PROTECTED_PORTS:
            raise InternalException(f"端口 {port} 受保护, 禁止释放")
        existing = self.get_by_value("port", str(port))
        if existing is None:
            raise InternalException(f"端口 {port} 未在 cg_resources 表中")
        return self.update(existing["id"], status="free",
                           owner_service_id=None, owner_project_id=None,
                           reserved_until=None)


__all__ = [
    "CodegardenResourceRepository",
    "VALID_RESOURCE_TYPES",
    "VALID_RESOURCE_STATUSES",
    "PORT_RANGE_START",
    "PORT_RANGE_END",
    "PROTECTED_PORTS",
]
