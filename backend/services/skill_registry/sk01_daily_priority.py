"""v1.0 T14 SK-01 daily-priority-intel — 今日重点情报聚合.

对应 contracts SK-01 + EXECUTION_GUIDE §T14 §1 第 1 点 "为六能力完成标准 schema".
T07 已落 admission_log / signals / admission_decisions (migration 097), SK-01 复用其聚合,
不新建表; T08 watchlist 走 SettingsRepository (subject_ids 列表).

设计:
  - compute(subject_id=None, watchlist=None) → 拼 admission_log + signals 聚合
  - 调 dsh (mock 注入可, 默认 ai_hub.generate_text) → 返 top_items + watchlist_changes + suggested_actions
  - 走 V1EvidenceService 落 receipt (best-effort, entity_type=knowledge 警告不影响)
  - 失败模式: dsh 解析失败 / 拉数据超时 / 依赖未就绪 → 返 fallback (仅 raw 聚合, 不出 dsh 摘要)
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from backend.logging_config import logger
from backend.repository.db import get_connection
from backend.services.dsh_adapter import run_dsh_sync


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _query_admission_recent(days: int = 7) -> list[dict[str, Any]]:
    """T07 已落 admission_log (migration 097), SK-01 拉近 N 天决策.

    真实列 = id / material_id / body_hash / verdict / reason / matched_rule_id /
    raw_material_json / created_at (无 action/subject_id)。原 SELECT 引用了不存在
    的列 → OperationalError 被吞 → 聚合自 T14 起静默为空, 本处随映射链一并修正;
    material_id 供 source_refs 反查 hotspot。
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT material_id, verdict, reason, created_at "
            "FROM admission_log "
            "WHERE created_at >= datetime('now', ?) "
            "ORDER BY created_at DESC LIMIT 20",
            (f"-{days} days",),
        ).fetchall()
    except sqlite3.OperationalError as e:
        logger.warning(f"admission_log table missing: {e}")
        return []
    return [
        {"material_id": r[0], "verdict": r[1], "reason": r[2], "ts": r[3]}
        for r in rows
    ]


def _query_signals_recent(days: int = 3) -> list[dict[str, Any]]:
    """T05 已落 v1_signals (migration 096), SK-01 拉近 N 天事件."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, subject_id, material_id, confidence, summary, occurred_at "
            "FROM v1_signals "
            "WHERE occurred_at >= datetime('now', ?) "
            "ORDER BY occurred_at DESC LIMIT 20",
            (f"-{days} days",),
        ).fetchall()
    except sqlite3.OperationalError as e:
        logger.warning(f"v1_signals table missing: {e}")
        return []
    return [
        {"id": r[0], "subject_id": r[1], "material_id": r[2],
         "confidence": r[3], "summary": r[4], "occurred_at": r[5]}
        for r in rows
    ]


def _query_watchlist() -> list[str]:
    """T08 watchlist (SettingsRepository kv 'watchlist.subjects')."""
    try:
        from backend.repository.settings_repo import SettingsRepository
        v = SettingsRepository().get("watchlist.subjects", [])
        if isinstance(v, list):
            return [str(x) for x in v]
        return []
    except Exception as e:
        logger.warning(f"watchlist fetch failed: {e}")
        return []


def _query_interest_domains() -> list[str]:
    """DEV-0176 T0.5: 兴趣画像 (settings.kv 'interest.practice_domains'), 空 = 无画像."""
    try:
        from backend.repository.settings_repo import SettingsRepository
        v = SettingsRepository().get("interest.practice_domains", [])
        if isinstance(v, list):
            return [str(x) for x in v if x]
        return []
    except Exception as e:
        logger.warning(f"interest domains fetch failed: {e}")
        return []


def _partition_by_practice(
    top_items: list[Any], interest_domains: list[str],
) -> dict[str, list[Any]] | None:
    """DEV-0176 T0.5: top_items 附加 practice_domain 并按域分区.

    - 无画像 (interest_domains 空) → 返回 None (消费方单组渲染 = 现状)
    - 有画像 → {命中域: [item...], ..., "other": [其余 item...]}
      (降权不删: 未命中不丢弃, 归入 other)
    - 每个 item 就地附加 practice_domain 字段 (即时打标, title 纯函数)
    """
    from backend.services.auto_classifier import classify_practice_domain

    for item in top_items:
        if isinstance(item, dict):
            item["practice_domain"] = classify_practice_domain(
                [], title=str(item.get("title") or item.get("summary") or ""),
            )
    if not interest_domains:
        return None
    partitions: dict[str, list[Any]] = {}
    for item in top_items:
        pd = item.get("practice_domain") if isinstance(item, dict) else None
        key = pd if (pd and pd in interest_domains) else "other"
        partitions.setdefault(key, []).append(item)
    return partitions


def _attach_hotspot_ids(
    top_items: list[Any], signals_recent: list[dict[str, Any]], *, days: int = 30,
) -> None:
    """top_items.source_refs.material_id → hotspot id 反查, 就地附加 item_id.

    reaction 需真实 hotspot 行 id (interest_attribution_hint 单查 hotspots,
    非 hotspot id → no_domain 被丢弃)。material_id 内容寻址不可逆 → 遍历近窗
    hotspots 反算建表; signal_id → material_id 作二级兜底 (LLM 可能只抄 signal_id)。
    命中 → item["item_id"]; 未命中不附加 (前端降级为只读)。
    """
    from backend.services.v1_signal_bridge import material_id_for

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, url, title FROM hotspots "
            "WHERE COALESCE(fetched_at, published_at, ingested_at) >= datetime('now', ?) "
            "  AND title != '' AND url != ''",
            (f"-{days} days",),
        ).fetchall()
    except sqlite3.OperationalError as e:
        logger.warning(f"hotspot reverse lookup unavailable: {e}")
        return
    mat_to_hotspot = {material_id_for(r["url"], r["title"]): r["id"] for r in rows}
    sig_to_mat = {
        str(s.get("id") or ""): str(s.get("material_id") or "")
        for s in signals_recent if s.get("id")
    }
    for item in top_items:
        if not isinstance(item, dict):
            continue
        for ref in item.get("source_refs") or []:
            if not isinstance(ref, dict):
                continue
            mid = str(ref.get("material_id") or "")
            hid = mat_to_hotspot.get(mid) if mid else None
            if hid is None:
                sid = str(ref.get("signal_id") or "")
                hid = mat_to_hotspot.get(sig_to_mat.get(sid, "")) if sid else None
            if hid:
                item["item_id"] = hid
                break


class DailyPriorityIntelService:
    """SK-01 daily-priority-intel service.

    走 dsh (mock 注入可, 默认 ai_hub.generate_text) → top_items + watchlist_changes + suggested_actions.
    """

    def __init__(self, *, dsh_caller: Callable[[str], str] | None = None) -> None:
        self._dsh_caller = dsh_caller

    def compute(
        self, subject_id: str | None = None, *,
        watchlist: list[str] | None = None,
        admission_days: int = 7, signals_days: int = 3,
    ) -> dict[str, Any]:
        """SK-01 主路径: 聚合 admission + signals → 调 dsh → 返 top_items + watchlist_changes + suggested_actions.

        Returns
        -------
        dict 含 top_items (≥1) / watchlist_changes (list) / suggested_actions (list) / generated_at / mode.
        """
        watchlist = watchlist if watchlist is not None else _query_watchlist()
        interest_domains = _query_interest_domains()
        admission_recent = _query_admission_recent(admission_days)
        signals_recent = _query_signals_recent(signals_days)
        # 缺依赖 (无 admission / 无 signals): 返 fallback (仅 raw 聚合, 不出 dsh 摘要)
        if not admission_recent and not signals_recent:
            return {
                "top_items": [],
                "watchlist_changes": [],
                "suggested_actions": ["无可用 admission_log / v1_signals 数据 (依赖未就绪)"],
                "generated_at": _now_utc_iso(),
                "mode": "fallback_no_data",
                # DEV-0176 T0.5
                "interest_domains": interest_domains,
                "practice_partitions": None,
            }
        # 调 dsh
        from backend.services.ai_hub.prompts import (
            build_daily_priority_intel_prompt,
            parse_daily_priority_intel_response,
        )
        prompt = build_daily_priority_intel_prompt(
            subject_id=subject_id or "(全 subject 视角)",
            admission_recent=admission_recent,
            signals_recent=signals_recent,
            watchlist_subjects=watchlist,
        )
        try:
            raw = self._call_dsh(prompt)
            parsed = parse_daily_priority_intel_response(raw)
        except Exception as e:
            logger.warning(f"dsh call/parse failed, fallback raw aggregation: {e}")
            return {
                "top_items": [],
                "watchlist_changes": [],
                "suggested_actions": [f"dsh 调用失败 ({type(e).__name__}), 待 fallback 重试"],
                "generated_at": _now_utc_iso(),
                "mode": "fallback_dsh_failed",
                # DEV-0176 T0.5
                "interest_domains": interest_domains,
                "practice_partitions": None,
            }
        # 走 V1EvidenceService receipt (best-effort, T05 模式)
        try:
            from backend.services.v1_evidence_service import V1EvidenceService
            content_hash = str(hash(json.dumps(parsed, sort_keys=True, ensure_ascii=False)))
            intent = V1EvidenceService().create_intent(
                f"v1-sk01-daily-priority-intel-{content_hash[:16]}", "knowledge", parsed,
                submitted_by="sk01",
            )
            V1EvidenceService().commit_intent(intent["intent_id"], entity_id="sk01", projection=None)
        except Exception as e:
            logger.warning(f"V1EvidenceService trace failed (SK-01 still inserts): {e}")
        # DEV-0176 T0.5: 实践域打标 + 兴趣域分区 (无画像 = None, 单组渲染等于现状)
        top_items = parsed["top_items"]
        _attach_hotspot_ids(top_items, signals_recent)
        practice_partitions = _partition_by_practice(top_items, interest_domains)
        return {
            "top_items": top_items,
            "watchlist_changes": parsed["watchlist_changes"],
            "suggested_actions": parsed["suggested_actions"],
            "generated_at": _now_utc_iso(),
            "mode": "dsh",
            "interest_domains": interest_domains,
            "practice_partitions": practice_partitions,
        }

    def _call_dsh(self, prompt: str) -> str:
        """SK-01 调 dsh (settings.kv 切换 mock/stdio/http). 失败兜底 ai_hub (显式).

        C06 R07 fix + D3 节点降级: 同 judgment/action/knowledge.
        """
        if self._dsh_caller is not None:
            return self._dsh_caller(prompt)
        from backend.services.dsh_adapter import DSHVendorUnavailableError
        try:
            return run_dsh_sync(
                prompt, task="daily_priority_intel", timeout_s=30.0,
                caller_service="sk01", dsh_caller=None,
            )
        except DSHVendorUnavailableError as e:
            logger.warning(
                "sk01._call_dsh D3 exit_criteria: 真 vendor 不可用, "
                "fallback 到 ai_hub (确定性协调器); commit_sha=%s; err=%s",
                e.commit_sha, e,
            )
        try:
            import asyncio

            from backend.services.ai_hub.service import ai_service
            return asyncio.run(ai_service.generate_text(
                messages=[{"role": "user", "content": prompt}],
                task="daily_priority_intel", max_tokens=4000, temperature=0.2,
            ))
        except Exception as e2:
            raise RuntimeError(
                f"dsh (D3 exit_criteria triggered) + ai_hub both failed: {e2}"
            ) from e2
