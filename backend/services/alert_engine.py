"""v1.7 Phase 12 — 告警引擎: 3 种规则类型评估 + 重复检测.

AlertEngine 是一个独立引擎, 不替代 Phase 3 的 alert_service.py.
它评估 3 种规则类型, 将结果写入 alert_events 表:

- tech_stack_cve: 新 CVE 命中 cg_projects.tech_stack
- critical_cve:   NVD CVSS ≥ 9.0 的 CVE
- bid_match:      标讯关键词命中 tech_stack

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
from typing import Any, Optional

from backend.repository.db import get_connection

logger = logging.getLogger("hotspot.alert_engine")


class AlertEngine:
    """Alert rule engine - evaluates 3 types of rules against recent data."""

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
        if rule_type == "tech_stack_cve":
            return self._evaluate_tech_stack_cve(rule)
        elif rule_type == "critical_cve":
            return self._evaluate_critical_cve(rule)
        elif rule_type == "bid_match":
            return self._evaluate_bid_match(rule)
        logger.warning("unknown rule_type", extra={"trace_id": "", "rule_type": rule_type})
        return 0

    # ------------------------------------------------------------------
    # Rule 1: tech_stack_cve
    # ------------------------------------------------------------------
    def _evaluate_tech_stack_cve(self, rule: dict[str, Any]) -> int:
        """Rule 1: New CVE hits cg_projects.tech_stack.

        Queries recent knowledge_items with CVE IDs, matches against
        non-archived cg_projects.tech_stack (JSON array of stack names).
        """
        config = self._parse_config(rule)
        window_hours = int(config.get("window_hours", 24))

        # 1. Load project tech stacks
        project_tech_stacks = self._load_project_tech_stacks()
        if not project_tech_stacks:
            return 0

        # 2. Query recent knowledge items with CVE IDs
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()
        conn = get_connection()
        cve_rows = conn.execute(
            "SELECT id, title, cve_ids, source_url FROM knowledge_items "
            "WHERE cve_ids IS NOT NULL AND cve_ids != '[]' AND ingested_at >= ? "
            "ORDER BY ingested_at DESC LIMIT 200",
            (cutoff,),
        ).fetchall()

        triggered = 0
        for row in cve_rows:
            r = dict(row)
            cve_ids = self._parse_cve_ids(r.get("cve_ids"))
            if not cve_ids:
                continue

            title_lower = (r.get("title") or "").lower()

            for cve_id in cve_ids:
                cve_lower = str(cve_id).lower()
                for pid, pinfo in project_tech_stacks.items():
                    for stack in pinfo["stacks"]:
                        if stack in title_lower or stack in cve_lower:
                            if self._trigger_alert(
                                rule_type="tech_stack_cve",
                                title=f"技术栈 CVE 影响: {cve_id}",
                                description=(
                                    f"CVE {cve_id} 影响项目 {pinfo['name']} "
                                    f"的技术栈 {stack}"
                                ),
                                severity="high",
                                source=cve_id,
                                source_url=r.get("source_url"),
                                item_id=r.get("id"),
                                project_id=pid,
                            ):
                                triggered += 1
                            break  # one alert per CVE per project
        return triggered

    # ------------------------------------------------------------------
    # Rule 2: critical_cve
    # ------------------------------------------------------------------
    def _evaluate_critical_cve(self, rule: dict[str, Any]) -> int:
        """Rule 2: Critical CVE (CVSS >= configured threshold).

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
            "SELECT id, title, cve_ids, source_url FROM knowledge_items "
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
    # Rule 3: bid_match
    # ------------------------------------------------------------------
    def _evaluate_bid_match(self, rule: dict[str, Any]) -> int:
        """Rule 3: Bid/procurement keywords hit tech_stack.

        Queries hotspots with category='bid', matches against
        non-archived cg_projects.tech_stack.
        """
        config = self._parse_config(rule)
        window_hours = int(config.get("window_hours", 24))

        cutoff = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()
        conn = get_connection()

        # 1. Load project tech stacks
        project_rows = conn.execute(
            "SELECT id, name, tech_stack FROM cg_projects "
            "WHERE status NOT IN ('archived', 'deprecated')"
        ).fetchall()

        tech_stacks: set[str] = set()
        project_map: dict[str, list[int]] = {}
        for row in project_rows:
            r = dict(row)
            ts_raw = r.get("tech_stack")
            if ts_raw:
                stacks = self._parse_json_array(ts_raw)
                for s in stacks:
                    s_lower = str(s).lower().strip()
                    if s_lower:
                        tech_stacks.add(s_lower)
                        project_map.setdefault(s_lower, []).append(r["id"])

        if not tech_stacks:
            return 0

        # 2. Query recent bid items from hotspots
        bid_rows = conn.execute(
            "SELECT id, title, summary, url FROM hotspots "
            "WHERE category = 'bid' AND ingested_at >= ? "
            "ORDER BY ingested_at DESC LIMIT 200",
            (cutoff,),
        ).fetchall()

        triggered = 0
        for row in bid_rows:
            r = dict(row)
            title = (r.get("title") or "").lower()
            summary = (r.get("summary") or "").lower()
            text = f"{title} {summary}"

            matched_stacks = [s for s in tech_stacks if s in text]
            if not matched_stacks:
                continue

            project_ids: set[int] = set()
            for s in matched_stacks:
                project_ids.update(project_map.get(s, []))

            self._trigger_alert(
                rule_type="bid_match",
                title=f"标讯技术栈匹配: {', '.join(matched_stacks[:3])}",
                description=(
                    f"标讯 '{r.get('title', '')[:80]}' 命中技术栈: "
                    f"{', '.join(matched_stacks)}"
                ),
                severity="medium",
                source=r.get("title", ""),
                source_url=r.get("url"),
                item_id=r.get("id"),
                project_id=next(iter(project_ids)) if project_ids else None,
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
        source: Optional[str] = None,
        source_url: Optional[str] = None,
        item_id: Optional[str] = None,
        project_id: Optional[int] = None,
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
                source, source_url, item_id, project_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rule_id,
                rule_type,
                title,
                description,
                severity,
                source,
                source_url,
                item_id,
                project_id,
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

    def _load_project_tech_stacks(self) -> dict[int, dict[str, Any]]:
        """Load non-archived project tech stacks.

        Returns:
            dict mapping project_id → {name, stacks: [lowercase stack names]}
        """
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, name, tech_stack FROM cg_projects "
            "WHERE status NOT IN ('archived', 'deprecated')"
        ).fetchall()

        result: dict[int, dict[str, Any]] = {}
        for row in rows:
            r = dict(row)
            ts_raw = r.get("tech_stack")
            stacks = self._parse_json_array(ts_raw) if ts_raw else []
            if stacks:
                result[r["id"]] = {
                    "name": r["name"],
                    "stacks": [s.lower() for s in stacks],
                }
        return result

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

    @staticmethod
    def _parse_json_array(raw: Any) -> list[str]:
        """Parse a JSON array from string, or return as-is if already a list."""
        if isinstance(raw, list):
            return [str(s) for s in raw]
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(s) for s in parsed]
            except (TypeError, ValueError):
                pass
            return [raw]
        return []