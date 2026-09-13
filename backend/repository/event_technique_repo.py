"""MP-2 事件类型实例化 Repository — 4 表 (单文件 4 repo, 避免膨胀)。

设计
----
- **IncidentReportRepo**: report CRUD + checksum/sha256 去重
- **EventTechniqueCandidateRepo**: 候选池 CRUD (含按 owner_status / event_type_id 过滤)
- **EventTechniqueMapRepo**: 终态 CRUD (技战法链渲染)
- **EventTypeRepo**: event_types 种子表 CRUD (MP-2 期基本只读)
- **Mp2AuditRepo**: audit_log_mp2_review 审计写入 (独立于 audit_log)

约束
----
- 所有 repo 复用 ``get_connection()`` 线程本地连接
- INSERT/UPDATE 失败抛 ``InternalException`` (项目级错误契约)
- 不引外键依赖 attack_techniques (解耦 MP-1, service 层 enforce)
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.db import get_connection


def _now_iso() -> str:
    """ISO-8601 UTC string."""
    return datetime.now(timezone.utc).isoformat()


def _compute_checksum(report_md: str) -> str:
    """sha256 hex digest of report body (用于 incident_reports.checksum 去重)."""
    return hashlib.sha256(report_md.encode("utf-8")).hexdigest()


def new_ulid(prefix: str = "id") -> str:
    """跨 repo/service 共享的 id 生成器 (timestamp ms + sha256 rand, 32 hex chars)."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    rand = hashlib.sha256(f"{prefix}{ts}{datetime.now(timezone.utc).timestamp()}".encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{ts}{rand}"


# ---------------------------------------------------------------------------
# IncidentReportRepo
# ---------------------------------------------------------------------------
class IncidentReportRepo:
    """CRUD for ``incident_reports`` 表."""

    def upsert(
        self,
        source_url: str,
        title: str,
        fetched_at: str,
        report_md: str,
        report_date: str | None = None,
        event_class_hint: str | None = None,
        agent_owner: str = "A",
    ) -> str:
        """按 source_url UNIQUE 去重, 已存在则返回原 id (无变更)。返回 report id (ULID 派生)."""
        conn = get_connection()
        checksum = _compute_checksum(report_md)
        existing = conn.execute(
            "SELECT id FROM incident_reports WHERE source_url = ?", (source_url,)
        ).fetchone()
        if existing:
            return str(existing["id"])
        # ULID 简化版 (32 hex chars = 16 random bytes + timestamp ms hex)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        rand = hashlib.sha256(f"{source_url}{ts}".encode("utf-8")).hexdigest()[:16]
        rid = f"ir_{ts}{rand}"
        try:
            conn.execute(
                """
                INSERT INTO incident_reports (
                    id, source_url, title, fetched_at, report_date,
                    event_class_hint, report_md, checksum, agent_owner
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rid, source_url, title, fetched_at, report_date,
                    event_class_hint, report_md, checksum, agent_owner,
                ),
            )
        except Exception as e:
            logger.error("incident_reports upsert failed: %s", e)
            raise InternalException(f"incident_reports upsert failed: {e}") from e
        return rid

    def get(self, report_id: str) -> dict | None:
        conn = get_connection()
        row = conn.execute(
            """
            SELECT id, source_url, title, fetched_at, report_date, event_class_hint,
                   report_md, checksum, agent_owner, created_at
            FROM incident_reports WHERE id = ?
            """,
            (report_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_by_source_url(self, source_url: str) -> dict | None:
        conn = get_connection()
        row = conn.execute(
            """
            SELECT id, source_url, title, fetched_at, report_date, event_class_hint,
                   report_md, checksum, agent_owner, created_at
            FROM incident_reports WHERE source_url = ?
            """,
            (source_url,),
        ).fetchone()
        return dict(row) if row else None

    def list_by_class(self, event_class_hint: str, limit: int = 50) -> list[dict]:
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT id, source_url, title, fetched_at, report_date, event_class_hint,
                   agent_owner, created_at
            FROM incident_reports WHERE event_class_hint = ? ORDER BY fetched_at DESC LIMIT ?
            """,
            (event_class_hint, int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# EventTechniqueCandidateRepo
# ---------------------------------------------------------------------------
class EventTechniqueCandidateRepo:
    """CRUD for ``event_technique_candidates`` 表."""

    def insert(
        self,
        candidate_id: str,
        event_type_id: str,
        technique_id: str,
        stage: str,
        confidence: float,
        evidence_quote: str,
        rationale: str | None,
        source_report_id: str,
        llm_model: str,
        llm_run_at: str,
        agent_owner: str = "A",
    ) -> None:
        """Insert a candidate. UNIQUE (event_type_id, technique_id, source_report_id)
        二次 insert 抛 IntegrityError → 上层捕获."""
        conn = get_connection()
        try:
            conn.execute(
                """
                INSERT INTO event_technique_candidates (
                    id, event_type_id, technique_id, stage, confidence, evidence_quote,
                    rationale, source_report_id, llm_model, llm_run_at, agent_owner
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate_id, event_type_id, technique_id, stage, float(confidence),
                    evidence_quote, rationale, source_report_id, llm_model, llm_run_at,
                    agent_owner,
                ),
            )
        except Exception as e:
            # UNIQUE 冲突由 service 层 catch + 处理; 其它错误向上抛
            logger.warning(
                "candidate insert failed (likely UNIQUE conflict): %s",
                str(e)[:200],
            )
            raise

    def update_owner_status(
        self,
        candidate_id: str,
        new_status: str,
        owner_action_by: str = "owner",
        reject_reason: str | None = None,
    ) -> None:
        conn = get_connection()
        try:
            conn.execute(
                """
                UPDATE event_technique_candidates SET
                    owner_status = ?,
                    owner_action_at = ?,
                    owner_action_by = ?,
                    reject_reason = ?
                WHERE id = ?
                """,
                (new_status, _now_iso(), owner_action_by, reject_reason, candidate_id),
            )
        except Exception as e:
            logger.error("candidate update failed: %s", e)
            raise InternalException(f"candidate update failed: {e}") from e

    def list_by_event_type(
        self, event_type_id: str, owner_status: str | None = None, limit: int = 200
    ) -> list[dict]:
        conn = get_connection()
        params: list = [event_type_id]
        sql = """
            SELECT id, event_type_id, technique_id, stage, confidence, evidence_quote,
                   rationale, source_report_id, llm_model, llm_run_at,
                   owner_status, owner_action_at, owner_action_by, reject_reason,
                   auto_reject_reason, agent_owner
            FROM event_technique_candidates WHERE event_type_id = ?
        """
        if owner_status:
            sql += " AND owner_status = ?"
            params.append(owner_status)
        sql += " ORDER BY confidence DESC LIMIT ?"
        params.append(int(limit))
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def list_pending_grouped_by_event_type(self) -> list[dict]:
        """按 event_type_id 分组统计 pending / approved / rejected 数量 (供 review UI 进度条)."""
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT event_type_id,
                   SUM(CASE WHEN owner_status = 'pending' THEN 1 ELSE 0 END) AS pending,
                   SUM(CASE WHEN owner_status = 'approved' THEN 1 ELSE 0 END) AS approved,
                   SUM(CASE WHEN owner_status = 'rejected' THEN 1 ELSE 0 END) AS rejected,
                   SUM(CASE WHEN owner_status = 'edited' THEN 1 ELSE 0 END) AS edited,
                   COUNT(*) AS total,
                   AVG(confidence) AS avg_confidence
            FROM event_technique_candidates
            GROUP BY event_type_id
            ORDER BY event_type_id
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def count_by_event_type(self, event_type_id: str) -> dict:
        conn = get_connection()
        row = conn.execute(
            """
            SELECT
                SUM(CASE WHEN owner_status = 'pending' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN owner_status = 'approved' THEN 1 ELSE 0 END) AS approved,
                SUM(CASE WHEN owner_status = 'rejected' THEN 1 ELSE 0 END) AS rejected,
                COUNT(*) AS total
            FROM event_technique_candidates WHERE event_type_id = ?
            """,
            (event_type_id,),
        ).fetchone()
        return dict(row) if row else {"pending": 0, "approved": 0, "rejected": 0, "total": 0}

    def get(self, candidate_id: str) -> dict | None:
        conn = get_connection()
        row = conn.execute(
            """
            SELECT id, event_type_id, technique_id, stage, confidence, evidence_quote,
                   rationale, source_report_id, llm_model, llm_run_at,
                   owner_status, owner_action_at, owner_action_by, reject_reason,
                   auto_reject_reason, agent_owner
            FROM event_technique_candidates WHERE id = ?
            """,
            (candidate_id,),
        ).fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# EventTechniqueMapRepo
# ---------------------------------------------------------------------------
class EventTechniqueMapRepo:
    """CRUD for ``event_technique_map`` 表 (owner 审定终态)."""

    def insert(
        self,
        map_id: str,
        event_type_id: str,
        technique_id: str,
        stage: str,
        note: str | None,
        candidate_id: str | None,
        source_report_id: str | None,
        approved_by: str = "owner",
        agent_owner: str = "A",
        audit_chain: list[dict] | None = None,
    ) -> None:
        conn = get_connection()
        try:
            conn.execute(
                """
                INSERT INTO event_technique_map (
                    id, event_type_id, technique_id, stage, note, candidate_id,
                    source_report_id, approved_at, approved_by, owner_audit_chain, agent_owner
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    map_id, event_type_id, technique_id, stage, note, candidate_id,
                    source_report_id, _now_iso(), approved_by,
                    json.dumps(audit_chain or [], ensure_ascii=False), agent_owner,
                ),
            )
        except Exception as e:
            logger.warning("event_technique_map insert failed: %s", str(e)[:200])
            raise

    def list_by_event_type(self, event_type_id: str) -> list[dict]:
        """渲染技战法卡用: 按 stage 时间线排序."""
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT id, event_type_id, technique_id, stage, note,
                   candidate_id, source_report_id, approved_at, approved_by,
                   owner_audit_chain, agent_owner
            FROM event_technique_map WHERE event_type_id = ?
            ORDER BY technique_id ASC, stage ASC
            """,
            (event_type_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def trace_chain(self, map_id: str) -> dict | None:
        """回溯 map → candidate → incident_report → source_url."""
        conn = get_connection()
        row = conn.execute(
            """
            SELECT m.id AS map_id, m.event_type_id, m.technique_id, m.stage,
                   m.candidate_id, m.source_report_id, m.approved_at, m.approved_by,
                   c.confidence AS candidate_confidence, c.evidence_quote AS candidate_evidence,
                   c.owner_status AS candidate_status,
                   r.source_url, r.title, r.checksum, r.report_md
            FROM event_technique_map m
            LEFT JOIN event_technique_candidates c ON c.id = m.candidate_id
            LEFT JOIN incident_reports r ON r.id = m.source_report_id
            WHERE m.id = ?
            """,
            (map_id,),
        ).fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# EventTypeRepo (MP-2 期基本只读)
# ---------------------------------------------------------------------------
class EventTypeRepo:
    """CRUD for ``event_types`` 表 (种子)."""

    def list_all(
        self,
        category: str | None = None,
        agent_owner: str | None = None,
    ) -> list[dict]:
        conn = get_connection()
        sql = "SELECT id, name_zh, name_en, category, agent_owner, priority, description, typical_signals, kill_chain_stages, report_source_pool, status FROM event_types WHERE 1=1"
        params: list = []
        if category:
            sql += " AND category = ?"
            params.append(category)
        if agent_owner:
            sql += " AND agent_owner = ?"
            params.append(agent_owner)
        sql += " ORDER BY category, priority DESC, id"
        rows = conn.execute(sql, params).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            # parse JSON fields
            for k in ("typical_signals", "kill_chain_stages", "report_source_pool"):
                try:
                    d[k] = json.loads(d[k]) if isinstance(d[k], str) else d[k]
                except (json.JSONDecodeError, TypeError):
                    d[k] = []
            results.append(d)
        return results

    def get(self, event_type_id: str) -> dict | None:
        conn = get_connection()
        row = conn.execute(
            "SELECT id, name_zh, name_en, category, agent_owner, priority, description, typical_signals, kill_chain_stages, report_source_pool, status FROM event_types WHERE id = ?",
            (event_type_id,),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        for k in ("typical_signals", "kill_chain_stages", "report_source_pool"):
            try:
                d[k] = json.loads(d[k]) if isinstance(d[k], str) else d[k]
            except (json.JSONDecodeError, TypeError):
                d[k] = []
        return d


# ---------------------------------------------------------------------------
# Mp2AuditRepo
# ---------------------------------------------------------------------------
class Mp2AuditRepo:
    """审计写入 — 与 audit_log 物理隔离, 不污染全局审计流."""

    def write(
        self,
        actor: str,
        action: str,
        target_type: str,
        target_id: str,
        event_type_id: str | None = None,
        detail: dict | None = None,
        trace_id: str | None = None,
    ) -> int:
        conn = get_connection()
        try:
            cursor = conn.execute(
                """
                INSERT INTO audit_log_mp2_review (
                    actor, action, target_type, target_id, event_type_id, detail, trace_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    actor, action, target_type, target_id, event_type_id,
                    json.dumps(detail or {}, ensure_ascii=False),
                    trace_id,
                ),
            )
            return int(cursor.lastrowid or 0)
        except Exception as e:
            logger.error("audit_log_mp2_review write failed: %s", e)
            raise InternalException(f"audit write failed: {e}") from e

    def list_by_target(self, target_id: str, limit: int = 50) -> list[dict]:
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT id, actor, action, target_type, target_id, event_type_id,
                   detail, trace_id, occurred_at
            FROM audit_log_mp2_review WHERE target_id = ?
            ORDER BY occurred_at DESC LIMIT ?
            """,
            (target_id, int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]


__all__ = [
    "IncidentReportRepo",
    "EventTechniqueCandidateRepo",
    "EventTechniqueMapRepo",
    "EventTypeRepo",
    "Mp2AuditRepo",
    "_compute_checksum",
    "_now_iso",
    "new_ulid",
]
