"""MP-2 IncidentReportService — 报告语料入库 (含校验 + 去重).

职责
----
- ``ingest_report(source_url, title, fetched_at, report_md, ...)``: 落 incident_reports, 按 source_url 去重
- ``get_report(report_id)``: 按 id 取报告 (含 report_md 全文, 给 evidence_quote 校验用)
- ``list_reports_by_event_type(event_type_id)``: 给 review 工具/前端列报告
- ``bulk_ingest_from_dir(dir_path, event_type_id, agent_owner)``: 从 data/security/incidents/agent_X/ 批量入库 (scripts 跑)

设计
----
- 校验: report_md 必须为非空字符串, ≥50 字 (避免空 report 入库)
- 去重: incident_reports.source_url UNIQUE 兜底 (幂等)
- agent_owner: 标识哪个 agent 提交, 主会话 merge 时按 A→E 顺序, 不同 agent 不会冲突
"""
from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.exceptions import InvalidParamException, NotFoundException
from backend.logging_config import logger
from backend.repository.event_technique_repo import IncidentReportRepo

# 报告原文最小长度 (避免空摘要入库)
MIN_REPORT_BODY_LEN = 50


def _normalize_text(s: str) -> str:
    """Unicode NFKC + 去多余空白 — 用于 evidence_quote substring 校验 (normalized form C)."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = " ".join(s.split())  # collapse all whitespace
    return s


class IncidentReportService:
    """薄 service — 直接复用 IncidentReportRepo, 加业务校验."""

    def __init__(self) -> None:
        self.repo = IncidentReportRepo()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def ingest_report(
        self,
        source_url: str,
        title: str,
        fetched_at: str,
        report_md: str,
        report_date: str | None = None,
        event_class_hint: str | None = None,
        agent_owner: str = "A",
    ) -> dict:
        """入库一份报告. 返回 {id, source_url, new: bool}.

        Raises:
            BadRequestException: report_md 太短 (<50字) 或 URL 非法.
        """
        if not source_url or not isinstance(source_url, str):
            raise InvalidParamException("source_url 必须为非空字符串")
        if not report_md or len(report_md.strip()) < MIN_REPORT_BODY_LEN:
            raise InvalidParamException(
                f"report_md 太短 (<{MIN_REPORT_BODY_LEN}字), 避免空摘要入库"
            )

        # 检查是否已存在 (idempotent)
        existing = self.repo.get_by_source_url(source_url)
        if existing:
            return {
                "id": existing["id"],
                "source_url": existing["source_url"],
                "new": False,
            }

        rid = self.repo.upsert(
            source_url=source_url,
            title=title or "",
            fetched_at=fetched_at or datetime.now(timezone.utc).isoformat(),
            report_md=report_md,
            report_date=report_date,
            event_class_hint=event_class_hint,
            agent_owner=agent_owner,
        )
        logger.info(
            "incident_report ingested",
            extra={"trace_id": "", "report_id": rid, "source_url": source_url},
        )
        return {"id": rid, "source_url": source_url, "new": True}

    def get_report(self, report_id: str) -> dict:
        row = self.repo.get(report_id)
        if not row:
            raise NotFoundException(f"report {report_id} not found")
        return row

    def list_reports_by_event_type(self, event_type_id: str, limit: int = 50) -> list[dict]:
        return self.repo.list_by_class(event_type_id, limit=limit)

    def bulk_ingest_from_dir(
        self,
        dir_path: Path,
        event_type_id: str,
        agent_owner: str = "A",
    ) -> dict:
        """批量入库 — 从目录读所有 .md 文件, frontmatter 解析 source_url/title/fetched_at/report_date.

        Frontmatter 格式:
          ---
          source_url: <URL>
          title: <title>
          fetched_at: <ISO 8601>
          report_date: <YYYY-MM-DD>
          ---

        Returns:
            {"total": N, "ingested": X, "skipped_existing": Y, "errors": [...]}
        """
        if not dir_path.exists():
            raise NotFoundException(f"directory not found: {dir_path}")

        md_files = sorted(dir_path.glob("*.md"))
        if not md_files:
            logger.warning("no .md files in %s", dir_path)
            return {"total": 0, "ingested": 0, "skipped_existing": 0, "errors": []}

        ingested = 0
        skipped = 0
        errors: list[dict[str, Any]] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        for md_file in md_files:
            try:
                content = md_file.read_text(encoding="utf-8")
                front, body = _split_frontmatter(content)
                source_url = front.get("source_url", "").strip()
                title = front.get("title", md_file.stem).strip()
                fetched_at = front.get("fetched_at", now_iso).strip()
                report_date = front.get("report_date", "").strip() or None

                if not source_url:
                    # 兜底: 用 stable 文件名当 source_url (避免版权问题)
                    source_url = f"mp2-agent-{agent_owner}-local://{md_file.stem}"

                if not body or len(body.strip()) < MIN_REPORT_BODY_LEN:
                    errors.append({"file": str(md_file), "error": "body too short"})
                    continue

                result = self.ingest_report(
                    source_url=source_url,
                    title=title,
                    fetched_at=fetched_at,
                    report_md=body,
                    report_date=report_date,
                    event_class_hint=event_type_id,
                    agent_owner=agent_owner,
                )
                if result["new"]:
                    ingested += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.error("bulk ingest error %s: %s", md_file, e)
                errors.append({"file": str(md_file), "error": str(e)})

        logger.info(
            "bulk ingest done",
            extra={
                "trace_id": "",
                "dir": str(dir_path),
                "total": len(md_files),
                "ingested": ingested,
                "skipped": skipped,
                "errors": len(errors),
            },
        )
        return {
            "total": len(md_files),
            "ingested": ingested,
            "skipped_existing": skipped,
            "errors": errors,
        }


# ---------------------------------------------------------------------------
# Frontmatter helpers (私有 — 不导出)
# ---------------------------------------------------------------------------
def _split_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """极简 YAML frontmatter 解析 (只支持 key: value 单行).

    兼容:
        ---
        source_url: https://...
        title: ...
        ---
        <body>
    """
    if not content.startswith("---"):
        return {}, content

    # 找第二个 ---
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    front_raw = parts[1].strip()
    body = parts[2].lstrip("\n")

    front: dict[str, str] = {}
    for line in front_raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        front[key.strip()] = val.strip()

    return front, body


__all__ = ["MIN_REPORT_BODY_LEN", "IncidentReportService", "_normalize_text"]
