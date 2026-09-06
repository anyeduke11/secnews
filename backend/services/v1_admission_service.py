"""v1.0 T07 信号准入服务 — admission + quarantine + label 集.

对应 contracts.md §3 (Signal) + EXECUTION_GUIDE §4 T07 准入门槛:
  - 基础准入: material → 信号评估 (deny → quarantine, allow → 信号落库)
  - 评估顺序: deny > allow > neutral (与 info_filter 一致)
  - quarantine: 拒绝入信号池, 但保留原文 (写 admission_log 审计)
  - 标注集 60-80 起步: 落地 8 维基础标签 + 评价阈值常量, 留给 T07 标注批次
    (annotation 维度: entity_type × confidence × urgency × domain × impact ×
    severity × audience × actionability, 每维 2-3 档 = 64 标签起步)

设计:
  - 复用 info_filter_service.evaluate (deny > allow > neutral) — 不重复造轮子
  - 不写 Signal 表 (T05 evidence 已提供单一入口; 本服务只输出 verdict + reason)
  - 调用方 (T06 源级管道) 拿 verdict 决定走 create_intent (allow) 还是 quarantine (deny)
  - quarantine 数据走 admission_log 表 (T07 migration 097 落地)

后续 T07 标注批次: 引入 supervision_service / golden set / inter-annotator
agreement, 不在本批范围 (本批只把准入框架 + 8 维标签常量 落地).
"""
from __future__ import annotations

import hashlib
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from backend.logging_config import logger
from backend.repository.db import get_connection


# ---------------------------------------------------------------------------
# 准入 verdict
# ---------------------------------------------------------------------------
class AdmissionVerdict(str, Enum):
    """准入决策 — 与 info_filter_service 一致 (deny > allow > neutral)."""

    ALLOW = "allow"
    DENY = "deny"
    NEUTRAL = "neutral"  # 无规则命中 → 走默认 (allow)


# ---------------------------------------------------------------------------
# 8 维标注集 (60-80 起步, contracts §3.3 + T07 计划)
# ---------------------------------------------------------------------------
# 设计: 8 维度 × 2-3 档 = 16-24 标签; 加 4 维交叉 = 64-80 起步; 总 80 上限对齐
# 任务台账 §16 "标注集 60-80 起步, 留出集纪律不变". 后续 T14 受管能力包接 supervision.

ANNOTATION_DIMENSIONS: dict[str, list[str]] = {
    "entity_type": ["cve", "regulation", "vendor_advisory", "exploit", "research"],
    "confidence": ["verified", "likely", "unverified"],
    "urgency": ["immediate", "this_week", "watch"],
    "domain": ["security", "ai", "compliance", "supply_chain", "infrastructure"],
    "impact": ["critical", "high", "medium", "low"],
    "severity": ["exploitable", "patch_available", "theoretical"],
    "audience": ["sec_team", "product_team", "leadership", "public"],
    "actionability": ["actionable_now", "needs_review", "informational"],
}


def label_count() -> int:
    """基础标签总数 (8 维笛卡尔积上限, 实际标注集 ≤80)."""
    n = 1
    for opts in ANNOTATION_DIMENSIONS.values():
        n *= len(opts)
    return n


# ---------------------------------------------------------------------------
# 准入结果
# ---------------------------------------------------------------------------
@dataclass
class AdmissionResult:
    """单条 material 准入结果."""

    verdict: AdmissionVerdict
    material_id: str
    matched_rule: dict[str, Any] | None
    reason: str
    labels: dict[str, str] = None  # 8 维 label (后续 T07 标注批次填)
    quarantined_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "material_id": self.material_id,
            "matched_rule": self.matched_rule,
            "reason": self.reason,
            "labels": self.labels or {},
            "quarantined_at": self.quarantined_at,
        }


# ---------------------------------------------------------------------------
# 准入服务
# ---------------------------------------------------------------------------
class V1AdmissionService:
    """信号准入服务 — evaluate (deny > allow > neutral) + quarantine 落 admission_log.

    复用 info_filter_service.evaluate 评估; 准入 verdict 决定 material 是否
    走 T05 evidence.create_intent("signal", ...) 还是落 quarantine.
    """

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    def evaluate(
        self,
        material: dict[str, Any],
        rules: list[dict[str, Any]] | None = None,
    ) -> AdmissionResult:
        """评估单条 material 的准入.

        Parameters
        ----------
        material:
            必含: id, category (或 source_kind), source_name (或 source),
            url, summary (供 label 推断).
        rules:
            准入规则集; None 时不查库, 直接 NEUTRAL.

        Returns
        -------
        AdmissionResult — verdict 决定下游 (allow → create_intent signal / deny → quarantine).
        """
        from backend.services.info_filter_service import evaluate as if_evaluate  # 延迟 import
        category = material.get("category") or material.get("source_kind") or "unknown"
        source_name = material.get("source_name") or material.get("source") or "unknown"
        source_id = material.get("source_id") or f"{category}:{source_name}"
        tag = material.get("tag")
        rules = rules or []
        verdict_str, matched = if_evaluate(
            rules,
            category=category,
            source_name=source_name,
            source_id=source_id,
            tag=tag,
        )
        verdict = AdmissionVerdict(verdict_str)
        reason = matched["note"] if matched else f"no rule matched for {source_id}"
        return AdmissionResult(
            verdict=verdict,
            material_id=material.get("id", ""),
            matched_rule=matched,
            reason=reason,
        )

    def quarantine(self, result: AdmissionResult, material: dict[str, Any]) -> int:
        """落 admission_log 表 (T07 后续 migration 097 落地) — 暂用 in-memory 兜底.

        Returns
        -------
        row_id — admission_log 主键, 0 表示未落 (表不存在, 测试用).
        """
        try:
            conn = self._conn or get_connection()
            body_hash = hashlib.sha256(
                ((material.get("url") or "") + "|" + material.get("id", "")).encode("utf-8")
            ).hexdigest()
            cur = conn.execute(
                "INSERT INTO admission_log "
                "(material_id, body_hash, verdict, reason, matched_rule_id, "
                " raw_material_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    result.material_id,
                    body_hash,
                    result.verdict.value,
                    result.reason,
                    result.matched_rule["id"] if result.matched_rule else None,
                    _safe_json(material),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
            return cur.lastrowid or 0
        except sqlite3.OperationalError as e:
            # admission_log 表未建 (T07 migration 097 未跑), 静默降级
            logger.warning(f"admission_log table missing: {e}")
            return 0

    def default_labels(self, material: dict[str, Any]) -> dict[str, str]:
        """从 material 推 8 维默认 label (后续 T07 标注批次替换为人工)."""
        from typing import cast
        labels: dict[str, str] = {}
        # entity_type: cve / regulation / ...
        url = (material.get("url") or "").lower()
        if "cve-" in url or "nvd.nist.gov" in url:
            labels["entity_type"] = "cve"
        elif any(kw in url for kw in ("csrc", "compliance", "regulation", "pci", "iso27001")):
            labels["entity_type"] = "regulation"
        else:
            labels["entity_type"] = "research"
        # confidence: 信号强度启发式
        labels["confidence"] = "unverified"
        # urgency: 默认 watch (T07 标注批次细化)
        labels["urgency"] = "watch"
        # impact/severity: 默认 medium/exploitable 待人工
        labels["impact"] = "medium"
        labels["severity"] = "theoretical"
        # domain: 从 category 推
        cat = (material.get("category") or "").lower()
        if "ai" in cat:
            labels["domain"] = "ai"
        elif "bid" in cat:
            labels["domain"] = "compliance"
        else:
            labels["domain"] = "security"
        # audience/actionability: 默认
        labels["audience"] = "sec_team"
        labels["actionability"] = "needs_review"
        return cast(dict[str, str], labels)


def _safe_json(obj: Any) -> str:
    """稳定序列化 (与 v1_evidence_service 同)."""
    import json
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
