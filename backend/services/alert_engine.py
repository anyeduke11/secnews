"""v1.7 Phase 12 — 告警引擎: 规则类型评估 + 重复检测.

AlertEngine 是一个独立引擎, 不替代 Phase 3 的 alert_service.py.
它评估规则 (DEV-0183: 原 bid_match 已随标讯下线移除), 将结果写入 alert_events 表:

- critical_cve:   NVD CVSS ≥ 9.0 的 CVE

2026-11-19 (四域删除): tech_stack_cve 规则随 CodeGarden 域退役 —
数据源 cg_projects 已被 migration 137 DROP, 该规则类型不再评估
(存量规则行由 137 置 enabled=0, 命中 _evaluate_rule 的 unknown 分支)。

设计决策:
- 使用 knowledge_items.cve_ids (JSON 数组) 作为 CVE 信息来源
  (security_entities 表存储 CVE 实体, metadata 含 cvss 评分)
- 重复检测: 同一 source + rule_type 在 24h 内不重复触发
- 日志: logger = logging.getLogger("hotspot.alert_engine")
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.repository.db import get_connection, knowledge_items_table

logger = logging.getLogger("hotspot.alert_engine")


class AlertEngine:
    """Alert rule engine - evaluates alert rules against recent data."""

    def __init__(self) -> None:
        self.rules = self._load_rules()

    # ------------------------------------------------------------------
    # Rule loading
    # ------------------------------------------------------------------
    def _load_rules(self) -> list[dict[str, Any]]:
        """Load enabled rules from alert_rule_definitions table."""
        conn = get_connection()
        cur = conn.execute(
            "SELECT * FROM alert_rule_definitions WHERE enabled = 1"
        )
        return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def evaluate_all(self) -> dict[str, int]:
        """Evaluate all rules, return trigger statistics.

        Returns:
            dict mapping rule name → number of new alerts triggered.
        """
        results: dict[str, int] = {}
        for rule in self.rules:
            try:
                count = self._evaluate_rule(rule)
                results[rule["name"]] = count
                if count > 0:
                    logger.info(
                        "rule triggered alerts",
                        extra={
                            "trace_id": "",
                            "rule_name": rule["name"],
                            "rule_type": rule["rule_type"],
                            "count": count,
                        },
                    )
            except Exception:
                logger.exception(
                    "rule evaluation failed",
                    extra={
                        "trace_id": "",
                        "rule_name": rule["name"],
                        "rule_type": rule["rule_type"],
                    },
                )
                results[rule["name"]] = -1
        return results

    def _evaluate_rule(self, rule: dict[str, Any]) -> int:
        """Evaluate a single rule."""
        rule_type = rule["rule_type"]
        if rule_type == "critical_cve":
            return self._evaluate_critical_cve(rule)
        # DEV-0183: "bid_match" 规则已随标讯下线移除 (存量 bid 规则走 unknown 分支)
        # 2026-11-19: "tech_stack_cve" 随 CodeGarden 域退役 (cg_projects 已 DROP)
        logger.warning("unknown rule_type", extra={"trace_id": "", "rule_type": rule_type})
        return 0

    # ------------------------------------------------------------------
    # Rule: critical_cve
    # ------------------------------------------------------------------
    def _evaluate_critical_cve(self, rule: dict[str, Any]) -> int:
        """Rule: Critical CVE (CVSS >= configured threshold).

        Queries security_entities (entity_type='CVE') with CVSS score
        in metadata JSON.  Falls back to knowledge_items.cve_ids for
        items without a security_entity record.
        """
        config = self._parse_config(rule)
        min_cvss = float(config.get("min_cvss", 9.0))

        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        conn = get_connection()

        # Primary path: security_entities with CVSS ≥ threshold
        rows = conn.execute(
            "SELECT id, name, description, metadata, external_ref "
            "FROM security_entities "
            "WHERE entity_type = 'CVE' "
            "AND json_extract(metadata, '$.cvss') IS NOT NULL "
            "AND CAST(json_extract(metadata, '$.cvss') AS REAL) >= ? "
            "AND created_at >= ? "
            "ORDER BY json_extract(metadata, '$.cvss') DESC LIMIT 100",
            (min_cvss, cutoff),
        ).fetchall()

        triggered = 0
        for row in rows:
            r = dict(row)
            cve_id = r.get("name") or r.get("id") or ""
            # Parse metadata JSON string to dict
            metadata_raw = r.get("metadata")
            if isinstance(metadata_raw, str):
                try:
                    metadata = json.loads(metadata_raw)
                except (TypeError, ValueError):
                    metadata = {}
            else:
                metadata = metadata_raw or {}
            cvss = metadata.get("cvss", "?")
            description = (
                f"CVSS 评分 {cvss} "
                f"- {r.get('description', '')[:200] or cve_id}"
            )
            if self._trigger_alert(
                rule_type="critical_cve",
                title=f"关键 CVE 告警: {cve_id}",
                description=description,
                severity="critical",
                source=cve_id,
                source_url=r.get("external_ref"),
                item_id=r.get("id"),
            ):
                triggered += 1

        # Secondary path: knowledge_items with CVE IDs (no security_entity CVSS)
        ki_rows = conn.execute(
            f"SELECT id, title, cve_ids, source_url FROM {knowledge_items_table()} "
            "WHERE cve_ids IS NOT NULL AND cve_ids != '[]' AND ingested_at >= ? "
            "ORDER BY ingested_at DESC LIMIT 200",
            (cutoff,),
        ).fetchall()

        for row in ki_rows:
            r = dict(row)
            cve_ids = self._parse_cve_ids(r.get("cve_ids"))
            if not cve_ids:
                continue
            for cve_id in cve_ids:
                # Avoid duplicates already triggered via security_entities
                if self._has_recent_alert("critical_cve", cve_id, 24):
                    continue
                self._trigger_alert(
                    rule_type="critical_cve",
                    title=f"关键 CVE 告警: {cve_id}",
                    description=f"CVSS 评分未知 - {r.get('title', '')[:100]}",
                    severity="critical",
                    source=cve_id,
                    source_url=r.get("source_url"),
                    item_id=r.get("id"),
                )
                triggered += 1

        return triggered

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _trigger_alert(
        self,
        rule_type: str,
        title: str,
        description: str,
        severity: str,
        source: str | None = None,
        source_url: str | None = None,
        item_id: str | None = None,
    ) -> int:
        """Write an alert event to the alert_events table.

        Includes duplicate detection: same source + rule_type within 24h
        will not create a new alert.

        Returns:
            alert event ID, or 0 if duplicate/skipped.
        """
        # Duplicate check: same source + rule_type within 24h
        if source:
            dup = self._has_recent_alert(rule_type, source, 24)
            if dup:
                logger.debug(
                    "duplicate alert skipped",
                    extra={
                        "trace_id": "",
                        "rule_type": rule_type,
                        "source": source,
                    },
                )
                return 0

        conn = get_connection()
        # Find the rule_id from alert_rule_definitions
        rule_row = conn.execute(
            "SELECT id FROM alert_rule_definitions "
            "WHERE rule_type = ? AND enabled = 1 LIMIT 1",
            (rule_type,),
        ).fetchone()
        rule_id = rule_row["id"] if rule_row else None

        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            """INSERT INTO alert_events
               (rule_id, rule_type, title, description, severity,
                source, source_url, item_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rule_id,
                rule_type,
                title,
                description,
                severity,
                source,
                source_url,
                item_id,
                now,
            ),
        )
        return cursor.lastrowid or 0

    def _has_recent_alert(self, rule_type: str, source: str, hours: int = 24) -> bool:
        """Check if an alert with the same rule_type + source exists within N hours."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        conn = get_connection()
        row = conn.execute(
            "SELECT 1 FROM alert_events "
            "WHERE rule_type = ? AND source = ? AND created_at >= ? LIMIT 1",
            (rule_type, source, cutoff),
        ).fetchone()
        return row is not None

    @staticmethod
    def _parse_config(rule: dict[str, Any]) -> dict[str, Any]:
        """Parse rule.config from JSON string or dict."""
        raw = rule.get("config")
        if raw is None:
            return {}
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (TypeError, ValueError):
                return {}
        return {}

    @staticmethod
    def _parse_cve_ids(raw: Any) -> list[str]:
        """Parse CVE IDs from JSON array, comma-separated string, or list."""
        if not raw:
            return []
        if isinstance(raw, list):
            return [str(c) for c in raw if c]
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(c) for c in parsed if c]
                return [raw]
            except (TypeError, ValueError):
                return [raw]
        return [str(raw)]

