"""v1_signal_bridge — hotspots 主采集流 → v1_signals 主路径桥 (v0.8.6 P1-2a)。

侦查定稿 (DEV-0267, 生产实证): ai_scores=0 非评分器故障 — knowledge_items 0 行
(kl:raw 无米, T1 永不评分; gateway.score 链路完好) + 唯一 intake 源 SecWiki feed
停更, 单源撑不起 signals ≥120/30d。本桥把 hotspots 增量经语义门分流进 v1 证据链
与 kl:raw, 喂活 T1 评分链 (ai_scores>0 为 P1-2 T4 真门前置)。

链路 (全部现成件装配, 本模块只做编排):
    hotspots (24h 窗口) → V1AdmissionService.evaluate (info_filter 语义门, gate 默认开)
      → deny    → quarantine (admission_log 留痕, 不产信号)
      → allow/neutral
          → v1_materials 镜像 (mat+sha256(url|title), 与 V1IngestBridge 同构幂等)
          → v1_signals (unverified)
          → knowledge_items stub (lifecycle=kl:raw) → T1 评分 → ai_scores

挂载: v1_signal_intake_tick_job 尾部 (collect.py; 零新 job / 零注册面变更)。
幂等: material id 内容寻址 (url|title 跨窗口稳定); signal key = v1-signal-{mat_id};
      kl stub id 内容寻址 (hotspot id 派生) — 三者重复轮全走 IdempotentReplay/upsert。
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.logging_config import logger

_BRIDGE_NAME = "hotspot-bridge"
_WINDOW_HOURS = 24
_BATCH_LIMIT = 50


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_candidates(window_hours: int, limit: int) -> list[dict[str, Any]]:
    """近窗 hotspots 增量 — 已镜像条目靠 mat id 幂等跳过, 不设状态表。"""
    from backend.repository.db import get_connection

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()
    rows = get_connection().execute(
        "SELECT id, title, summary, source, url, category, published_at, fetched_at "
        "FROM hotspots "
        "WHERE is_hidden = 0 AND title != '' AND url != '' "
        "  AND COALESCE(fetched_at, published_at, ingested_at) >= ? "
        "ORDER BY fetched_at DESC LIMIT ?",
        (cutoff, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def _material_body(hotspot: dict[str, Any]) -> dict[str, Any]:
    """hotspot → v1_materials body (契约对齐 V1IngestBridge._parse_entry)。"""
    title = str(hotspot.get("title") or "").strip()
    url = str(hotspot.get("url") or "").strip()
    summary = str(hotspot.get("summary") or "").strip()[:400]
    source = str(hotspot.get("source") or "")
    return {
        "id": "mat" + _sha(f"{url}|{title}")[:24],
        "source_kind": "url",
        "url": url,
        "title": title,
        "content_hash": _sha(f"{title}|{url}|{summary}"),
        "content_length": len(title) + len(summary),
        "summary": summary,
        "published_at": hotspot.get("published_at") or hotspot.get("fetched_at") or _now_iso(),
        "fetched_by": f"v1-bridge:{source}",
        # 准入辅助字段 (evaluate 约定)
        "category": str(hotspot.get("category") or "unknown"),
        "source_name": source,
        "source_id": f"hotspot:{source}",
    }


def run_hotspot_signal_bridge(
    *, window_hours: int = _WINDOW_HOURS, limit: int = _BATCH_LIMIT,
) -> dict[str, Any]:
    """P1-2a 主桥一轮: hotspots 增量 → 准入 → material+signal+kl:raw stub。

    Returns (job 侧只 log 不抛, 语义同 V1IngestBridge.run_intake_tick):
        {"candidates", "mirrored"(幂等跳过), "signals_committed",
         "signals_idempotent", "denied", "kl_stubs", "error"}
    """
    summary: dict[str, Any] = {
        "candidates": 0, "mirrored": 0, "signals_committed": 0,
        "signals_idempotent": 0, "denied": 0, "kl_stubs": 0, "error": None,
    }
    try:
        from backend.domain.knowledge_models import KnowledgeItem
        from backend.repository.db import get_connection
        from backend.repository.knowledge_repo import knowledge_repo
        from backend.services.info_filter_service import list_rules
        from backend.services.v1_admission_service import AdmissionVerdict, V1AdmissionService
        from backend.services.v1_evidence_service import IdempotentReplay, V1EvidenceService

        conn = get_connection()
        hotspot_rows = _fetch_candidates(window_hours, limit)
        summary["candidates"] = len(hotspot_rows)
        if not hotspot_rows:
            return summary

        # 已镜像 → 跳过 (内容寻址 id 稳定; 免重复 admission + 信号重放)
        bodies = [_material_body(h) for h in hotspot_rows]
        ids = [b["id"] for b in bodies]
        marks = ",".join("?" for _ in ids)
        known = {r[0] for r in conn.execute(
            f"SELECT id FROM v1_materials WHERE id IN ({marks})", ids).fetchall()}
        summary["mirrored"] = len(known)
        bodies = [b for b in bodies if b["id"] not in known]
        if not bodies:
            return summary

        try:
            rules = list_rules(conn, enabled_only=True)
        except Exception as e:  # 规则加载失败 → neutral 全放行 (不阻断主采集流)
            logger.warning(f"v1_signal_bridge rules load failed (neutral 放行): {e}")
            rules = []
        admission = V1AdmissionService(conn)
        evidence = V1EvidenceService(projection_dir=None)  # 只入库不落 wiki (D1 语义)
        ensured_subjects: set[str] = set()

        for body in bodies:
            result = admission.evaluate(body, rules=rules)
            admission.quarantine(result, body)  # 全量 verdict 落 admission_log
            if result.verdict is AdmissionVerdict.DENY:
                summary["denied"] += 1
                continue

            # 每源一个 subject (body 不含时间戳 → IdempotentReplay 幂等, 同 bridge)
            source_id = body["source_id"]
            if source_id not in ensured_subjects:
                subj_id = "subj-src-" + _sha(source_id)[:24]
                subj_body = {
                    "id": subj_id,
                    "entity_type": "other",
                    "canonical_name": f"信源: {body['source_name'] or source_id}",
                }
                try:
                    si = evidence.create_intent(
                        f"v1-subject-{source_id}", "subject", subj_body,
                        submitted_by=_BRIDGE_NAME,
                    )
                    evidence.commit_intent(si["intent_id"], entity_id=subj_id)
                except IdempotentReplay:
                    pass
                ensured_subjects.add(source_id)

            mat_id = body["id"]
            try:
                mi = evidence.create_intent(
                    f"v1-material-{mat_id}", "material", body,
                    submitted_by=_BRIDGE_NAME,
                )
                evidence.commit_intent(mi["intent_id"], entity_id=mat_id)
            except IdempotentReplay:
                pass  # 并发轮重放 — material 已在

            sig_id = "sig" + _sha(mat_id)[:24]
            signal_body = {
                "id": sig_id,
                "subject_id": "subj-src-" + _sha(source_id)[:24],
                "material_id": mat_id,
                "summary": body["summary"] or body["title"],
                "occurred_at": body["published_at"],
                "admission_rule_version": "info-filter@hotspot-bridge",
                "admission_reason": result.reason[:200],
                "confidence": "unverified",
                "status": "unverified",
            }
            try:
                gi = evidence.create_intent(
                    f"v1-signal-{mat_id}", "signal", signal_body,
                    submitted_by=_BRIDGE_NAME,
                )
                evidence.commit_intent(gi["intent_id"], entity_id=sig_id)
                summary["signals_committed"] += 1
            except IdempotentReplay:
                summary["signals_idempotent"] += 1

            # kl:raw stub — 喂 T1 评分链 (upsert 幂等)
            now = _now_iso()
            knowledge_repo.upsert_item(KnowledgeItem(
                id="kl-" + _sha(f"hotspot:{mat_id}")[:24],
                title=body["title"],
                source="secnews",
                source_url=body["url"],
                topic=body["summary"][:200] or None,
                lifecycle="kl:raw",
                ingested_at=now,
                updated_at=now,
            ))
            summary["kl_stubs"] += 1
    except Exception as e:  # 桥故障不反噬主采集流 (job 侧同款隔离)
        summary["error"] = f"{type(e).__name__}: {e}"
        logger.error(f"v1_signal_bridge crashed: {summary['error']}")
        return summary

    # P0-10 纪律: 空转 → 不在 INFO 噪声; 有产出 → INFO 可见 (loguru 风格 f-string, 同 bridge)
    if summary["signals_committed"] or summary["kl_stubs"]:
        logger.info(
            f"v1_signal_bridge: candidates={summary['candidates']} "
            f"mirrored={summary['mirrored']} signals+={summary['signals_committed']} "
            f"denied={summary['denied']} kl_stubs={summary['kl_stubs']}"
        )
    return summary


__all__ = ["run_hotspot_signal_bridge"]
