"""v1.7 Phase 3 — 告警规则与告警仓库.

对应迁移: 028_v1.7_alert_rules.sql
表结构:
  alert_rules(id, name, condition, action, cooldown_sec, enabled, last_fired_at, created_at, updated_at)
  alerts(id, rule_id, entity_type, entity_id, payload, status, created_at, processed_at)

注意: 实际迁移 schema 与 plan 代码片段 (cooldown_min / alerts.read) 不同,
以迁移文件为准 — 使用 cooldown_sec (INTEGER) / alerts.status (TEXT).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from backend.repository.db import get_connection


# ---------------------------------------------------------------------------
# AlertRuleRepository — alert_rules 表 CRUD
# ---------------------------------------------------------------------------
class AlertRuleRepository:
    """alert_rules 表的 CRUD 仓库 (实例无状态, 跨线程共享)."""

    def add(
        self,
        id: str,
        name: str,
        condition: dict,
        action: dict,
        cooldown_sec: int = 3600,
        enabled: bool = True,
    ) -> dict:
        """新建或替换一条规则 (INSERT OR REPLACE)."""
        now = datetime.now(timezone.utc).isoformat()
        get_connection().execute(
            """
            INSERT OR REPLACE INTO alert_rules
                (id, name, condition, action, cooldown_sec, enabled,
                 last_fired_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (
                id, name,
                json.dumps(condition, ensure_ascii=False),
                json.dumps(action, ensure_ascii=False),
                int(cooldown_sec),
                1 if enabled else 0,
                now, now,
            ),
        )
        return self.get(id)  # type: ignore[return-value]

    def get(self, id: str) -> Optional[dict]:
        row = get_connection().execute(
            "SELECT * FROM alert_rules WHERE id = ?", (id,)
        ).fetchone()
        return _row_to_rule(row) if row else None

    def list(self, enabled_only: bool = False) -> list[dict]:
        sql = "SELECT * FROM alert_rules"
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY created_at DESC"
        rows = get_connection().execute(sql).fetchall()
        return [_row_to_rule(r) for r in rows]

    def list_enabled(self) -> list[dict]:
        """列出所有启用的规则 (供 evaluate_hotspot 使用)."""
        return self.list(enabled_only=True)

    def update(
        self,
        id: str,
        name: Optional[str] = None,
        condition: Optional[dict] = None,
        action: Optional[dict] = None,
        cooldown_sec: Optional[int] = None,
        enabled: Optional[bool] = None,
    ) -> Optional[dict]:
        existing = self.get(id)
        if not existing:
            return None
        now = datetime.now(timezone.utc).isoformat()
        # condition/action: 未传则保留原值 (existing 已反序列化为 dict, 需重新 dumps)
        cond_val = json.dumps(condition, ensure_ascii=False) if condition is not None else json.dumps(existing["condition"], ensure_ascii=False)
        act_val = json.dumps(action, ensure_ascii=False) if action is not None else json.dumps(existing["action"], ensure_ascii=False)
        get_connection().execute(
            """
            UPDATE alert_rules
               SET name = ?, condition = ?, action = ?,
                   cooldown_sec = ?, enabled = ?, updated_at = ?
             WHERE id = ?
            """,
            (
                name if name is not None else existing["name"],
                cond_val,
                act_val,
                int(cooldown_sec) if cooldown_sec is not None else existing["cooldown_sec"],
                (1 if enabled else 0) if enabled is not None else existing["enabled"],
                now,
                id,
            ),
        )
        return self.get(id)

    def touch_last_fired(self, id: str, fired_at: Optional[str] = None) -> None:
        """更新规则的 last_fired_at (cooldown 检查依据)."""
        ts = fired_at or datetime.now(timezone.utc).isoformat()
        get_connection().execute(
            "UPDATE alert_rules SET last_fired_at = ?, updated_at = ? WHERE id = ?",
            (ts, ts, id),
        )

    def delete(self, id: str) -> int:
        cur = get_connection().execute("DELETE FROM alert_rules WHERE id = ?", (id,))
        return cur.rowcount or 0


# ---------------------------------------------------------------------------
# AlertRepository — alerts 表 (已触发告警实例) CRUD
# ---------------------------------------------------------------------------
class AlertRepository:
    """alerts 表的 CRUD 仓库."""

    def add(
        self,
        rule_id: str,
        entity_type: str = "",
        entity_id: str = "",
        payload: Optional[dict] = None,
    ) -> dict:
        """新建一条告警实例 (status=pending)."""
        aid = f"alert-{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        get_connection().execute(
            """
            INSERT INTO alerts
                (id, rule_id, entity_type, entity_id, payload, status, created_at, processed_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?, NULL)
            """,
            (
                aid, rule_id, entity_type, entity_id,
                json.dumps(payload or {}, ensure_ascii=False),
                now,
            ),
        )
        return self.get(aid)  # type: ignore[return-value]

    def get(self, id: str) -> Optional[dict]:
        row = get_connection().execute(
            "SELECT * FROM alerts WHERE id = ?", (id,)
        ).fetchone()
        return _row_to_alert(row) if row else None

    def list(
        self,
        status: Optional[str] = None,
        rule_id: Optional[str] = None,
        limit: int = 200,
    ) -> list[dict]:
        sql = "SELECT * FROM alerts WHERE 1=1"
        params: list = []
        if status:
            sql += " AND status = ?"
            params.append(status)
        if rule_id:
            sql += " AND rule_id = ?"
            params.append(rule_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = get_connection().execute(sql, params).fetchall()
        return [_row_to_alert(r) for r in rows]

    def mark_read(self, id: str) -> Optional[dict]:
        """标记告警为已读 (status=read)."""
        existing = self.get(id)
        if not existing:
            return None
        now = datetime.now(timezone.utc).isoformat()
        get_connection().execute(
            "UPDATE alerts SET status = 'read', processed_at = ? WHERE id = ?",
            (now, id),
        )
        return self.get(id)

    def mark_processed(self, id: str, status: str = "processed") -> Optional[dict]:
        """标记告警已处理 (status=processed/dismissed/read)."""
        existing = self.get(id)
        if not existing:
            return None
        now = datetime.now(timezone.utc).isoformat()
        get_connection().execute(
            "UPDATE alerts SET status = ?, processed_at = ? WHERE id = ?",
            (status, now, id),
        )
        return self.get(id)

    def delete(self, id: str) -> int:
        cur = get_connection().execute("DELETE FROM alerts WHERE id = ?", (id,))
        return cur.rowcount or 0

    def count(self, status: Optional[str] = None) -> int:
        sql = "SELECT COUNT(*) AS c FROM alerts"
        params: list = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        row = get_connection().execute(sql, params).fetchone()
        return int(row["c"] or 0)


# ---------------------------------------------------------------------------
# Row → dict helpers (反序列化 JSON 字段)
# ---------------------------------------------------------------------------
def _row_to_rule(row) -> dict:
    return {
        "id": str(row["id"]),
        "name": str(row["name"]),
        "condition": _parse_json(row["condition"], {}),
        "action": _parse_json(row["action"], {}),
        "cooldown_sec": int(row["cooldown_sec"] or 3600),
        "enabled": bool(row["enabled"]),
        "last_fired_at": row["last_fired_at"],
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def _row_to_alert(row) -> dict:
    return {
        "id": str(row["id"]),
        "rule_id": str(row["rule_id"]),
        "entity_type": row["entity_type"] or "",
        "entity_id": row["entity_id"] or "",
        "payload": _parse_json(row["payload"], {}),
        "status": str(row["status"]),
        "created_at": str(row["created_at"]),
        "processed_at": row["processed_at"],
    }


def _parse_json(raw, default):
    if raw is None or raw == "":
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default
