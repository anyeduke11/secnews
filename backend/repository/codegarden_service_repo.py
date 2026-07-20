"""Phase 2b CodeGarden 服务网格 — cg_services 表 CRUD + 多维筛选 + 自动发现 upsert.

设计要点
--------
- cg_services.id 用 TEXT UUID (与 cg_projects.id 一致)
- cg_services.project_id 外键 → cg_projects(id) ON DELETE CASCADE
- dependencies / env_vars 用 TEXT + json.dumps/loads
- upsert_from_scan: 由 name + endpoint_port 唯一识别一个扫描到的服务
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.db import get_connection


VALID_SERVICE_TYPES = ("http", "websocket", "grpc", "static", "database")
VALID_RUNTIMES = ("docker", "pm2", "system", "bare")
VALID_SERVICE_STATUSES = ("running", "stopped", "error", "unknown")
VALID_HEALTH_CHECK_TYPES = ("http", "tcp", "script")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def _parse_json(raw: Optional[str], default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _row_to_service(row: sqlite3.Row) -> dict:
    return {
        "id": str(row["id"]),
        "project_id": row["project_id"],
        "name": str(row["name"]),
        "namespace": row["namespace"],
        "type": str(row["type"]),
        "runtime": str(row["runtime"]),
        "status": str(row["status"]),
        "endpoint_host": row["endpoint_host"],
        "endpoint_port": row["endpoint_port"],
        "endpoint_domain": row["endpoint_domain"],
        "health_check_type": row["health_check_type"],
        "health_check_path": row["health_check_path"],
        "health_check_interval": int(row["health_check_interval"] or 30),
        "cpu_limit": row["cpu_limit"],
        "memory_limit": row["memory_limit"],
        "dependencies": _parse_json(row["dependencies"], []),
        "env_vars": _parse_json(row["env_vars"], {}),
        "created_at": str(row["created_at"]),
        "last_checked_at": row["last_checked_at"],
    }


class CodegardenServiceRepository:
    """cg_services 表 CRUD + 多维筛选 + upsert_from_scan."""

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    def create(
        self,
        *,
        name: str,
        type: str,
        runtime: str,
        status: str = "unknown",
        project_id: Optional[str] = None,
        namespace: Optional[str] = None,
        endpoint_host: Optional[str] = None,
        endpoint_port: Optional[int] = None,
        endpoint_domain: Optional[str] = None,
        health_check_type: Optional[str] = None,
        health_check_path: Optional[str] = None,
        health_check_interval: int = 30,
        cpu_limit: Optional[str] = None,
        memory_limit: Optional[str] = None,
        dependencies: Optional[list[str]] = None,
        env_vars: Optional[dict] = None,
    ) -> dict:
        if type not in VALID_SERVICE_TYPES:
            raise InternalException(
                f"type 必须为 {', '.join(VALID_SERVICE_TYPES)}; got {type!r}"
            )
        if runtime not in VALID_RUNTIMES:
            raise InternalException(
                f"runtime 必须为 {', '.join(VALID_RUNTIMES)}; got {runtime!r}"
            )
        if status not in VALID_SERVICE_STATUSES:
            raise InternalException(
                f"status 必须为 {', '.join(VALID_SERVICE_STATUSES)}; got {status!r}"
            )
        if health_check_type and health_check_type not in VALID_HEALTH_CHECK_TYPES:
            raise InternalException(
                f"health_check_type 必须为 {', '.join(VALID_HEALTH_CHECK_TYPES)}; got {health_check_type!r}"
            )
        if not name or not name.strip():
            raise InternalException("name 不能为空")

        service_id = _new_id()
        now = _now_iso()
        deps_json = json.dumps(dependencies or [], ensure_ascii=False)
        env_json = json.dumps(env_vars or {}, ensure_ascii=False)

        conn = get_connection()
        try:
            conn.execute("BEGIN")
            conn.execute(
                """
                INSERT INTO cg_services (
                    id, project_id, name, namespace, type, runtime, status,
                    endpoint_host, endpoint_port, endpoint_domain,
                    health_check_type, health_check_path, health_check_interval,
                    cpu_limit, memory_limit, dependencies, env_vars,
                    created_at, last_checked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    service_id, project_id, name.strip(), namespace, type, runtime,
                    status, endpoint_host, endpoint_port, endpoint_domain,
                    health_check_type, health_check_path, int(health_check_interval),
                    cpu_limit, memory_limit, deps_json, env_json, now, now,
                ),
            )
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error(f"cg_services create failed: {e}")
            raise InternalException(f"cg_services create failed: {e}") from e

        return self.get(service_id)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------
    def get(self, service_id: str) -> Optional[dict]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM cg_services WHERE id = ?", (service_id,)
        ).fetchone()
        return _row_to_service(row) if row else None

    def list(
        self,
        *,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        namespace: Optional[str] = None,
        type: Optional[str] = None,
        runtime: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        conn = get_connection()
        where: list[str] = []
        params: list = []
        if project_id:
            where.append("project_id = ?")
            params.append(project_id)
        if status:
            where.append("status = ?")
            params.append(status)
        if namespace:
            where.append("namespace = ?")
            params.append(namespace)
        if type:
            where.append("type = ?")
            params.append(type)
        if runtime:
            where.append("runtime = ?")
            params.append(runtime)
        if keyword:
            kw = keyword.strip()
            if kw:
                where.append("(name LIKE ? OR namespace LIKE ? OR endpoint_domain LIKE ?)")
                like_kw = f"%{kw}%"
                params.extend([like_kw, like_kw, like_kw])
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        total_row = conn.execute(
            f"SELECT COUNT(*) AS n FROM cg_services {where_sql}", params
        ).fetchone()
        total = int(total_row["n"]) if total_row else 0

        rows = conn.execute(
            f"""
            SELECT * FROM cg_services {where_sql}
            ORDER BY last_checked_at DESC NULLS LAST, created_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, int(limit), int(offset)),
        ).fetchall()
        return [_row_to_service(r) for r in rows], total

    # ------------------------------------------------------------------
    # 更新 / 删除
    # ------------------------------------------------------------------
    def update(self, service_id: str, **fields) -> dict:
        existing = self.get(service_id)
        if existing is None:
            raise InternalException(f"service {service_id} 不存在")

        allowed = {
            "name", "namespace", "type", "runtime", "status",
            "endpoint_host", "endpoint_port", "endpoint_domain",
            "health_check_type", "health_check_path", "health_check_interval",
            "cpu_limit", "memory_limit", "project_id", "last_checked_at",
        }
        json_fields = {"dependencies", "env_vars"}

        sets: list[str] = []
        params: list = []
        for k, v in fields.items():
            if v is None:
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

        params.append(service_id)

        conn = get_connection()
        try:
            conn.execute("BEGIN")
            conn.execute(
                f"UPDATE cg_services SET {', '.join(sets)} WHERE id = ?",
                params,
            )
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise InternalException(f"cg_services update failed: {e}") from e

        return self.get(service_id)  # type: ignore[return-value]

    def delete(self, service_id: str) -> bool:
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            cur = conn.execute(
                "DELETE FROM cg_services WHERE id = ?", (service_id,)
            )
            conn.execute("COMMIT")
            return cur.rowcount > 0
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise InternalException(f"cg_services delete failed: {e}") from e

    def set_status(self, service_id: str, status: str, note: Optional[str] = None) -> dict:
        if status not in VALID_SERVICE_STATUSES:
            raise InternalException(f"status 非法: {status!r}")
        return self.update(service_id, status=status, last_checked_at=_now_iso())

    # ------------------------------------------------------------------
    # 自动发现 — upsert_from_scan
    # ------------------------------------------------------------------
    def upsert_from_scan(
        self,
        *,
        name: str,
        type: str,
        runtime: str,
        status: str,
        endpoint_port: Optional[int] = None,
        endpoint_host: Optional[str] = None,
        namespace: Optional[str] = None,
    ) -> tuple[dict, bool]:
        """扫描结果 upsert: 以 (name, endpoint_port) 为唯一键.

        Returns (service, created) — created=True 表示新插入.
        """
        conn = get_connection()
        # 先按 (name, endpoint_port) 查找
        where_clauses = ["name = ?"]
        params: list = [name]
        if endpoint_port is not None:
            where_clauses.append("endpoint_port = ?")
            params.append(endpoint_port)
        else:
            where_clauses.append("endpoint_port IS NULL")
        row = conn.execute(
            f"SELECT * FROM cg_services WHERE {' AND '.join(where_clauses)} LIMIT 1",
            params,
        ).fetchone()

        now = _now_iso()
        if row is None:
            # 创建
            svc = self.create(
                name=name, type=type, runtime=runtime, status=status,
                endpoint_host=endpoint_host, endpoint_port=endpoint_port,
                namespace=namespace,
            )
            return svc, True
        else:
            # 更新 status + last_checked_at
            svc = self.update(
                str(row["id"]),
                status=status,
                last_checked_at=now,
                endpoint_host=endpoint_host or row["endpoint_host"],
            )
            return svc, False


__all__ = [
    "CodegardenServiceRepository",
    "VALID_SERVICE_TYPES",
    "VALID_RUNTIMES",
    "VALID_SERVICE_STATUSES",
    "VALID_HEALTH_CHECK_TYPES",
]
