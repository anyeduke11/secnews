"""CRM 商机仓库 (security-cockpit 方案 C, migration 071)。

含六态状态机迁移校验与事件留痕; 口径见 docs/COCKPIT_PRD.md §2。
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.repository.db import get_connection

#: 管线阶段顺序 (PRD §2 状态机); 赢单/输单为终态
STAGES: tuple[str, ...] = ("需求沟通", "方案提交", "商务谈判", "合同签订", "赢单", "输单")
ACTIVE_STAGES: tuple[str, ...] = ("需求沟通", "方案提交", "商务谈判", "合同签订")
TERMINAL_STAGES: tuple[str, ...] = ("赢单", "输单")

#: 合法迁移表: from → 允许的 to 集合
_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "需求沟通": ("方案提交", "输单"),
    "方案提交": ("商务谈判", "输单"),
    "商务谈判": ("合同签订", "输单"),
    "合同签订": ("赢单", "输单"),
    "赢单": (),
    "输单": (),
}


class InvalidTransitionError(Exception):
    """非法状态机迁移 (含终态再迁移 / 跨阶段跳跃)。"""


@dataclass
class CrmOpportunityRow:
    id: int
    customer_id: int
    name: str
    service_type: str
    stage: str
    amount: float
    cost: float
    owner: str
    expected_close_date: str | None
    description: str
    won_at: str | None
    lost_reason: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id, "customer_id": self.customer_id, "name": self.name,
            "service_type": self.service_type, "stage": self.stage,
            "amount": self.amount, "cost": self.cost, "owner": self.owner,
            "expected_close_date": self.expected_close_date,
            "description": self.description, "won_at": self.won_at,
            "lost_reason": self.lost_reason,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }


_OPP_FIELDS = ["id", "customer_id", "name", "service_type", "stage", "amount", "cost", "owner", "expected_close_date", "description", "won_at", "lost_reason", "created_at", "updated_at"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(r: sqlite3.Row) -> CrmOpportunityRow:
    d = {f: r[f] for f in _OPP_FIELDS}
    d["amount"] = float(d["amount"])
    d["cost"] = float(d["cost"])
    return CrmOpportunityRow(**d)


def create(data: dict) -> CrmOpportunityRow:
    conn = get_connection()
    now = _now_iso()
    fields = {
        f: data[f] for f in ["customer_id", "name", "service_type", "stage", "amount", "cost", "owner", "expected_close_date", "description"] if data.get(f) is not None
    }
    if not fields.get("stage"):
        fields["stage"] = "需求沟通"
    if fields["stage"] not in STAGES:
        raise ValueError(f"未知阶段: {fields['stage']} (允许: {list(STAGES)})")
    try:
        cur = conn.execute(
            f"INSERT INTO crm_opportunities ({', '.join(fields)}, created_at, updated_at) "
            f"VALUES ({', '.join('?' for _ in fields)}, ?, ?)",
            (*fields.values(), now, now),
        )
    except sqlite3.IntegrityError as e:
        raise ValueError(f"商机创建失败 (外键/约束): {e}") from e
    opp = get(cur.lastrowid)
    conn.execute(
        "INSERT INTO crm_opportunity_events (opportunity_id, from_stage, to_stage, note, created_at) "
        "VALUES (?, NULL, ?, 'created', ?)",
        (opp.id, opp.stage, now),
    )
    return opp


def get(opportunity_id: int) -> CrmOpportunityRow | None:
    conn = get_connection()
    r = conn.execute(
        f"SELECT {', '.join(_OPP_FIELDS)} FROM crm_opportunities WHERE id = ?",
        (int(opportunity_id),),
    ).fetchone()
    return _row(r) if r else None


def list_all(*, customer_id: int | None = None, stage: str | None = None,
             owner: str | None = None,
             limit: int = 200, offset: int = 0) -> list[CrmOpportunityRow]:
    conn = get_connection()
    where, params = [], []
    if customer_id is not None:
        where.append("customer_id = ?")
        params.append(int(customer_id))
    if stage:
        where.append("stage = ?")
        params.append(stage)
    if owner:
        where.append("owner = ?")
        params.append(owner)
    sql = f"SELECT {', '.join(_OPP_FIELDS)} FROM crm_opportunities"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
    params.extend((int(limit), int(offset)))
    return [_row(r) for r in conn.execute(sql, params)]


def transition(opportunity_id: int, to_stage: str, *, note: str = "",
               lost_reason: str = "") -> CrmOpportunityRow:
    """状态机推进: 校验合法迁移 → 更新 stage/won_at/lost_reason → 写事件。"""
    opp = get(opportunity_id)
    if opp is None:
        raise LookupError(f"商机不存在: {opportunity_id}")
    allowed = _TRANSITIONS.get(opp.stage, ())
    if to_stage not in allowed:
        raise InvalidTransitionError(
            f"非法迁移: {opp.stage} → {to_stage} (允许: {list(allowed) or '终态'})"
        )
    now = _now_iso()
    conn = get_connection()
    won_at = now if to_stage == "赢单" else opp.won_at
    conn.execute(
        "UPDATE crm_opportunities SET stage = ?, won_at = ?, lost_reason = ?, updated_at = ? WHERE id = ?",
        (to_stage, won_at, lost_reason if to_stage == "输单" else opp.lost_reason,
         now, int(opportunity_id)),
    )
    conn.execute(
        "INSERT INTO crm_opportunity_events (opportunity_id, from_stage, to_stage, note, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (int(opportunity_id), opp.stage, to_stage, note, now),
    )
    return get(opportunity_id)


def update_fields(opportunity_id: int, data: dict) -> CrmOpportunityRow | None:
    """非阶段字段的部分更新 (改阶段必须走 transition)。"""
    allowed = ["name", "service_type", "amount", "cost", "owner", "expected_close_date", "description", "lost_reason"]
    sets = [f for f in allowed if f in data]
    if sets:
        conn = get_connection()
        conn.execute(
            f"UPDATE crm_opportunities SET {', '.join(f'{c} = ?' for c in sets)}, updated_at = ? WHERE id = ?",
            (*(data[c] for c in sets), _now_iso(), int(opportunity_id)),
        )
    return get(opportunity_id)


def delete(opportunity_id: int) -> bool:
    conn = get_connection()
    cur = conn.execute("DELETE FROM crm_opportunities WHERE id = ?", (int(opportunity_id),))
    return cur.rowcount > 0


def events(opportunity_id: int, limit: int = 50) -> list[dict]:
    conn = get_connection()
    return [dict(r) for r in conn.execute(
        "SELECT id, opportunity_id, from_stage, to_stage, note, created_at "
        "FROM crm_opportunity_events WHERE opportunity_id = ? ORDER BY created_at DESC LIMIT ?",
        (int(opportunity_id), int(limit)),
    )]


__all__ = [
    "ACTIVE_STAGES",
    "STAGES",
    "TERMINAL_STAGES",
    "CrmOpportunityRow",
    "InvalidTransitionError",
    "create",
    "delete",
    "events",
    "get",
    "list_all",
    "transition",
    "update_fields",
]
