"""QualityCustomRulesRepository — quality_custom_rules (v0.8.6 P2) CRUD。

两层质量规则的自定义面存储 (owner 裁决 2026-10-04):
- rule_kind='expert'  — 确定性 matcher 规则 (ExpertRejectGate/ExpertFlagGate 消费)
- rule_kind='semantic' — NL 语义规则 (SemanticRulesGate 聚合单次 LLM 判别)

配置域 → main 库 (裸名, 非流水不进 warm)。单写者 = 本 repo (R2);
读写方 = quality_rules_api (CRUD/dry-run) + custom_rules_gate (执行)。
"""
from __future__ import annotations

import sqlite3
from typing import Any

from backend.repository.db import get_connection

MATCH_KINDS_EXPERT = (
    "title_contains", "source_in", "category_equals",
    "url_matches", "summary_len_lt",
)
ACTIONS = ("flag", "reject")


class QualityCustomRulesRepository:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    def _c(self) -> sqlite3.Connection:
        return self._conn or get_connection()

    def list_rules(
        self, *, kind: str | None = None, enabled_only: bool = False,
    ) -> list[dict[str, Any]]:
        sql = ("SELECT id, name, rule_kind, match_kind, match_value, action, "
               "deduction, scope_category, enabled, created_at, updated_at "
               "FROM quality_custom_rules")
        where, params = [], []
        if kind:
            where.append("rule_kind = ?")
            params.append(kind)
        if enabled_only:
            where.append("enabled = 1")
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id ASC"
        return [dict(r) for r in self._c().execute(sql, params).fetchall()]

    def create(
        self, *, name: str, rule_kind: str, match_kind: str, match_value: str,
        action: str = "flag", deduction: int = 10,
        scope_category: str = "", enabled: bool = True,
    ) -> dict[str, Any]:
        cur = self._c().execute(
            "INSERT INTO quality_custom_rules "
            "(name, rule_kind, match_kind, match_value, action, deduction, "
            " scope_category, enabled) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (name, rule_kind, match_kind, match_value, action,
             max(0, min(100, int(deduction))), scope_category,
             1 if enabled else 0),
        )
        self._c().commit()
        return self.get(int(cur.lastrowid))  # type: ignore[arg-type,return-value]

    def get(self, rule_id: int) -> dict[str, Any] | None:
        row = self._c().execute(
            "SELECT id, name, rule_kind, match_kind, match_value, action, "
            "deduction, scope_category, enabled, created_at, updated_at "
            "FROM quality_custom_rules WHERE id = ?",
            (int(rule_id),),
        ).fetchone()
        return dict(row) if row else None

    def update(self, rule_id: int, fields: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {
            "name", "match_kind", "match_value", "action",
            "deduction", "scope_category", "enabled",
        }
        sets, params = [], []
        for key, val in fields.items():
            if key not in allowed:
                continue
            if key == "deduction":
                val = max(0, min(100, int(val)))
            if key == "enabled":
                val = 1 if val else 0
            sets.append(f"{key} = ?")
            params.append(val)
        if not sets:
            return self.get(rule_id)
        sets.append("updated_at = datetime('now', 'localtime')")
        params.append(int(rule_id))
        self._c().execute(
            f"UPDATE quality_custom_rules SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        self._c().commit()
        return self.get(rule_id)

    def delete(self, rule_id: int) -> int:
        cur = self._c().execute(
            "DELETE FROM quality_custom_rules WHERE id = ?", (int(rule_id),),
        )
        self._c().commit()
        return cur.rowcount
