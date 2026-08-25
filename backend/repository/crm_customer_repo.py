"""CRM 客户主档仓库 (security-cockpit 方案 C, migration 071)。

字段口径见 docs/COCKPIT_PRD.md §2; 金额单位元, 时间 UTC isoformat。
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.repository.db import get_connection


class CrmCustomerExistsError(Exception):
    """客户名称唯一约束冲突 (name UNIQUE)。"""


@dataclass
class CrmCustomerRow:
    id: int
    name: str
    industry: str
    level: str
    status: str
    region: str
    owner: str
    contact_name: str
    contact_phone: str
    email: str
    contract_start_date: str | None
    contract_end_date: str | None
    contract_amount: float
    nps_score: int | None
    notes: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "industry": self.industry,
            "level": self.level, "status": self.status, "region": self.region,
            "owner": self.owner, "contact_name": self.contact_name,
            "contact_phone": self.contact_phone, "email": self.email,
            "contract_start_date": self.contract_start_date,
            "contract_end_date": self.contract_end_date,
            "contract_amount": self.contract_amount,
            "nps_score": self.nps_score, "notes": self.notes,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }


_CUSTOMER_FIELDS = ["id", "name", "industry", "level", "status", "region", "owner", "contact_name", "contact_phone", "email", "contract_start_date", "contract_end_date", "contract_amount", "nps_score", "notes", "created_at", "updated_at"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(r: sqlite3.Row) -> CrmCustomerRow:
    d = {f: r[f] for f in _CUSTOMER_FIELDS}
    d["contract_amount"] = float(d["contract_amount"])
    return CrmCustomerRow(**d)


def create(data: dict) -> CrmCustomerRow:
    conn = get_connection()
    now = _now_iso()
    fields = {
        f: data[f] for f in ["name", "industry", "level", "status", "region", "owner", "contact_name", "contact_phone", "email", "contract_start_date", "contract_end_date", "contract_amount", "nps_score", "notes"] if data.get(f) is not None
    }
    try:
        cur = conn.execute(
            f"INSERT INTO crm_customers ({', '.join(fields)}, created_at, updated_at) "
            f"VALUES ({', '.join('?' for _ in fields)}, ?, ?)",
            (*fields.values(), now, now),
        )
    except sqlite3.IntegrityError as e:
        raise CrmCustomerExistsError(str(e)) from e
    return get(cur.lastrowid)


def get(customer_id: int) -> CrmCustomerRow | None:
    conn = get_connection()
    r = conn.execute(
        f"SELECT {', '.join(_CUSTOMER_FIELDS)} FROM crm_customers WHERE id = ?",
        (int(customer_id),),
    ).fetchone()
    return _row(r) if r else None


def list_all(*, industry: str | None = None, status: str | None = None,
             level: str | None = None, q: str | None = None,
             limit: int = 200, offset: int = 0) -> list[CrmCustomerRow]:
    """列表; q 为名称/联系人模糊搜索。排序固定 updated_at DESC (T2 约束: 列表不丢新数据)。"""
    conn = get_connection()
    where, params = [], []
    if industry:
        where.append("industry = ?")
        params.append(industry)
    if status:
        where.append("status = ?")
        params.append(status)
    if level:
        where.append("level = ?")
        params.append(level)
    if q:
        where.append("(name LIKE ? OR contact_name LIKE ?)")
        params.extend((f"%{q}%", f"%{q}%"))
    sql = f"SELECT {', '.join(_CUSTOMER_FIELDS)} FROM crm_customers"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
    params.extend((int(limit), int(offset)))
    return [_row(r) for r in conn.execute(sql, params)]


def update(customer_id: int, data: dict) -> CrmCustomerRow | None:
    """白名单字段部分更新; 不触碰 created_at。"""
    allowed = ["name", "industry", "level", "status", "region", "owner", "contact_name", "contact_phone", "email", "contract_start_date", "contract_end_date", "contract_amount", "nps_score", "notes"]
    sets = [f for f in allowed if f in data]
    if not sets:
        return get(customer_id)
    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE crm_customers SET {', '.join(f'{c} = ?' for c in sets)}, updated_at = ? WHERE id = ?",
            (*(data[c] for c in sets), _now_iso(), int(customer_id)),
        )
    except sqlite3.IntegrityError as e:
        raise CrmCustomerExistsError(str(e)) from e
    return get(customer_id)


def delete(customer_id: int) -> bool:
    conn = get_connection()
    cur = conn.execute("DELETE FROM crm_customers WHERE id = ?", (int(customer_id),))
    return cur.rowcount > 0


def industries() -> list[str]:
    conn = get_connection()
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT industry FROM crm_customers ORDER BY industry"
    )]


__all__ = [
    "CrmCustomerExistsError",
    "CrmCustomerRow",
    "create",
    "delete",
    "get",
    "industries",
    "list_all",
    "update",
]
