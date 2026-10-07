"""v1_signal_bridge — hotspots 主采集流 → v1_signals 主路径桥 (v0.8.6 P1-2a)。

侦查定稿 (DEV-0267, 生产实证): ai_scores=0 非评分器故障 — knowledge_items 0 行
(kl:raw 无米, T1 永不评分; gateway.score 链路完好) + 唯一 intake 源 SecWiki feed
停更, 单源撑不起 signals ≥120/30d。本桥把 hotspots 增量经语义门分流进 v1 证据链
与 kl:raw, 喂活 T1 评分链 (ai_scores>0 为 P1-2 T4 真门前置)。

链路 (全部现成件装配, 本模块只做编排):
    hotspots (24h 窗口) → V1AdmissionService.evaluate (info_filter 语义门, gate 默认开)
      → deny    → quarantine (admission_log 留痕, 不产信号)
      → allow/neutral
          → gateway.score 评分前置 (DEV-0284 轨②: score < MIN_BRIDGE_SCORE=2.5
            → quarantine 留痕不产信号/stub; None=LLM 失败 fail-open 放行)
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
# DEV-0284 轨② (owner 三裁决 2026-10-04): 评分门槛 X=2.5 (0-10 刻度) —
# 显式低分 → deny + quarantine 留痕, 不产信号/kl:raw stub;
# score=None (LLM 失败) ≠ 低质量 → fail-open 产信号 (P0-6/E3 诚实语义)。
# 依据: 7d 桥评分 n=1449 中位 2.5, X=2.5 pass 52% → 转化率 ~0.18 (带内)。
MIN_BRIDGE_SCORE = 2.5


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_candidates(window_hours: int, limit: int) -> tuple[list[dict[str, Any]], int]:
    """近窗 hotspots 增量 — 全窗拉取后 Python 侧过滤已镜像再截 limit。

    修复 (DEV-0268 后记): 原 SQL LIMIT 先截断 + material 幂等跳过 → 桥永久
    卡在头部同一批 (fetched_at DESC 不变, mirrored 全命中 → 100% 跳过, 尾部
    候选永不轮转)。改为全窗拉取 (轻量 SELECT) → known 过滤 → 再截 limit。
    Returns (candidates, mirrored_skipped)。
    """
    from backend.repository.db import get_connection

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()
    rows = get_connection().execute(
        "SELECT id, title, summary, source, url, category, published_at, fetched_at "
        "FROM hotspots "
        "WHERE is_hidden = 0 AND title != '' AND url != '' "
        "  AND COALESCE(fetched_at, published_at, ingested_at) >= ? "
        "ORDER BY fetched_at DESC",
        (cutoff,),
    ).fetchall()
    hotspots = [dict(r) for r in rows]
    if not hotspots:
        return [], 0
    # material id = sha(url|title) — 窗口内先算先滤, 未镜像的才进批
    def _mat_id(h: dict[str, Any]) -> str:
        return "mat" + _sha(f"{str(h.get('url') or '').strip()}|{str(h.get('title') or '').strip()}")[:24]

    ids = [_mat_id(h) for h in hotspots]
    marks = ",".join("?" for _ in ids)
    known = {r[0] for r in get_connection().execute(
        f"SELECT id FROM v1_materials WHERE id IN ({marks})", ids).fetchall()}
    fresh = [h for h, mid in zip(hotspots, ids, strict=True) if mid not in known]
    return fresh[:limit], len(known)


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
        "signals_idempotent": 0, "denied": 0, "kl_stubs": 0,
        "scored": 0, "score_skipped": 0, "denied_by_score": 0,
        "error": None,
    }
    try:
        from backend.domain.knowledge_models import KnowledgeItem
        from backend.repository.db import get_connection
        from backend.repository.knowledge_repo import knowledge_repo
        from backend.services.ai_write_back import write_score
        from backend.services.info_filter_service import list_rules
        from backend.services.v1_admission_service import (
            AdmissionResult,
            AdmissionVerdict,
            V1AdmissionService,
        )
        from backend.services.v1_evidence_service import IdempotentReplay, V1EvidenceService

        conn = get_connection()
        fresh, mirrored_skipped = _fetch_candidates(window_hours, limit)
        summary["candidates"] = len(fresh)
        summary["mirrored"] = mirrored_skipped
        if not fresh:
            return summary

        # 已镜像已在 _fetch_candidates 内过滤 — bodies 即本轮新增
        bodies = [_material_body(h) for h in fresh]

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

            mat_id = body["id"]
            kl_id = "kl-" + _sha(f"hotspot:{mat_id}")[:24]

            # ── 轨② score-first (DEV-0284): 评分前置于信号产出 ──────────
            # ai_scores 是门槛输入, 也是 T4 真门依据 — 桥内评分与生命周期
            # 解耦的契约不变 (P1-2a), 只是次序提前。
            try:
                import asyncio as _asyncio

                from backend.services.ai_hub.gateway import llm_service

                score = _asyncio.run(llm_service.score(
                    f"{body['title']} {body['summary']}".strip(), kl_id,
                ))
                if score is not None:
                    write_score(kl_id, score, reason="v1-bridge", scorer="gateway.score")
                    summary["scored"] += 1
                else:
                    summary["score_skipped"] += 1
            except Exception as score_exc:  # 评分失败不阻断分流主链
                score = None
                summary["score_skipped"] += 1
                logger.debug(f"v1_signal_bridge score skipped: {score_exc}")

            # 评分门槛 (X=2.5): 显式低分 → deny + quarantine 留痕, 不产信号/stub。
            # score=None 走不到这里 (fail-open, LLM 失败 ≠ 低质量)。
            if score is not None and score < MIN_BRIDGE_SCORE:
                summary["denied_by_score"] += 1
                admission.quarantine(
                    AdmissionResult(
                        verdict=AdmissionVerdict.DENY,
                        material_id=mat_id,
                        matched_rule=None,
                        reason=f"score_below_threshold: {score:.1f} < {MIN_BRIDGE_SCORE}",
                    ),
                    body,
                )
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

            # kl:raw stub — 喂 T1 评分链 (upsert 幂等); 低分已被上部门槛拦下
            now = _now_iso()
            knowledge_repo.upsert_item(KnowledgeItem(
                id=kl_id,
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

    # P0-10 纪律: 空转 → 不在 INFO 噪声; 有产出 (含评分门槛拒) → INFO 可见
    if summary["signals_committed"] or summary["kl_stubs"] or summary["denied_by_score"]:
        logger.info(
            f"v1_signal_bridge: candidates={summary['candidates']} "
            f"mirrored={summary['mirrored']} signals+={summary['signals_committed']} "
            f"denied={summary['denied']} denied_score={summary['denied_by_score']} "
            f"kl_stubs={summary['kl_stubs']}"
        )
    return summary


__all__ = ["run_hotspot_signal_bridge"]
