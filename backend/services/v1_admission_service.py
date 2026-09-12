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
        """落 admission_log 表 — migration 097 落地后真写入 (不再静默返 0).

        Returns
        -------
        row_id — admission_log 主键; migration 未跑 / 表缺失时返 0 (兜底)
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
            # admission_log 表未建 (migration 097 未跑) — 兜底返 0, 与旧版语义兼容
            logger.warning(f"admission_log table missing: {e}")
            return 0

    def default_labels(self, material: dict[str, str]) -> dict[str, str]:
        """从 material 推 8 维默认 label (后续 T07 标注批次替换为人工).

        DEV-0179 (Workbench Focus P1.1 标签统一): domain 推断优先走
        ``auto_classifier.classify_domain`` (v0/v1 共享的单一分类事实源),
        命中失败再回退到既有 category 映射。
        """
        from typing import cast

        from backend.services.auto_classifier import classify_domain

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
        # domain: 共享分类器优先 (P1.1 标签统一), 值域必须在标注维度内,
        # 命中失败回退 category 映射
        shared = classify_domain(
            tags=[], title=material.get("title") or "", source_url=material.get("url") or "",
        )
        allowed_domains = set(ANNOTATION_DIMENSIONS["domain"])
        if shared in allowed_domains:
            labels["domain"] = shared
        else:
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

    # ------------------------------------------------------------------
    # 标注 API (T07 监督批次落地)
    # ------------------------------------------------------------------
    # 监督批次协议:
    #   - inter-annotator agreement (Cohen's Kappa / Krippendorff's α) 留 T07 监督批次
    #   - 当前 60-80 起步标注集是单人标注, 后续接 2 人独立标注 + agreement 计算
    #   - 所有 API 走 SQLite, 不引入新依赖

    def label(
        self,
        item_id: str,
        dimensions: dict[str, str],
        annotator: str,
        confidence: float = 0.9,
    ) -> int:
        """写入单条 material 的 8 维标注.

        Parameters
        ----------
        item_id:
            material_id (字符串, 与 admission_label.material_id 对齐).
        dimensions:
            {dimension: value} 字典; 全部 dimension 必须在 ANNOTATION_DIMENSIONS 内,
            value 必须在对应维度值域内, 否则抛 ValueError.
        annotator:
            human:<name> | agent:<id> — 后续 agreement 计算按 annotator 分组.
        confidence:
            0.0-1.0, 入库 CHECK.

        Returns
        -------
        label_id — admission_label 主键 (AUTOINCREMENT); 写入失败/表缺失返 0.

        Notes
        -----
        - 一次 label() 调用写多条记录 (一维一行), 便于多标注者并行累计;
        - 单条 material 同维度允许多行, 监督批次计算 agreement 时聚合.
        """
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"confidence 必须在 [0.0, 1.0], got {confidence}")
        _validate_dimensions(dimensions)
        try:
            conn = self._conn or get_connection()
            now = datetime.now(timezone.utc).isoformat()
            ids: list[int] = []
            for dim, val in dimensions.items():
                cur = conn.execute(
                    "INSERT INTO admission_label "
                    "(material_id, dimension, value, annotator, confidence, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (item_id, dim, val, annotator, confidence, now),
                )
                ids.append(cur.lastrowid or 0)
            conn.commit()
            return ids[0] if ids else 0  # 单条 label 返回第一条主键 (兼容旧调用方)
        except sqlite3.OperationalError as e:
            logger.warning(f"admission_label table missing: {e}")
            return 0

    def create_label_set(self, name: str, schema_version: str = "v1.0") -> int:
        """创建标注集 (一次监督批次 = 一个集).

        Returns
        -------
        set_id — admission_set.id; 表缺失返 0.

        Raises
        ------
        sqlite3.IntegrityError — name 重复 (UNIQUE).
        """
        try:
            conn = self._conn or get_connection()
            cur = conn.execute(
                "INSERT INTO admission_set (name, schema_version, item_count, created_at) "
                "VALUES (?, ?, 0, ?)",
                (name, schema_version, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            return cur.lastrowid or 0
        except sqlite3.OperationalError as e:
            logger.warning(f"admission_set table missing: {e}")
            return 0

    def add_to_set(
        self,
        set_id: int,
        material_id: str,
        labels: dict[str, str],
    ) -> int:
        """收录一条 material + label 到标注集.

        先写 admission_label (一维一行, 拿到 label_ids), 再写 admission_set_items,
        最后累加 admission_set.item_count.

        Returns
        -------
        first_label_id — 写入的第一条 admission_label 主键; 表缺失/集不存在返 0.

        Raises
        ------
        ValueError — labels 中含越界维度/值.
        """
        _validate_dimensions(labels)
        try:
            conn = self._conn or get_connection()
            now = datetime.now(timezone.utc).isoformat()
            cur_set = conn.execute(
                "SELECT id FROM admission_set WHERE id = ?", (set_id,)
            ).fetchone()
            if cur_set is None:
                raise ValueError(f"admission_set id={set_id} 不存在")
            label_ids: list[int] = []
            for dim, val in labels.items():
                cur = conn.execute(
                    "INSERT INTO admission_label "
                    "(material_id, dimension, value, annotator, confidence, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        material_id,
                        dim,
                        val,
                        f"set:{set_id}",  # 标注者 = set_id, 便于 agreement 计算时分组
                        0.9,
                        now,
                    ),
                )
                label_ids.append(cur.lastrowid or 0)
            for lid in label_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO admission_set_items "
                    "(set_id, material_id, label_id) VALUES (?, ?, ?)",
                    (set_id, material_id, lid),
                )
            conn.execute(
                "UPDATE admission_set SET item_count = "
                "(SELECT COUNT(DISTINCT material_id) FROM admission_set_items WHERE set_id = ?) "
                "WHERE id = ?",
                (set_id, set_id),
            )
            conn.commit()
            return label_ids[0] if label_ids else 0
        except sqlite3.OperationalError as e:
            logger.warning(f"admission_log tables missing: {e}")
            return 0

    def get_set_items(self, set_id: int) -> list[dict[str, Any]]:
        """拉取标注集内所有 (material, label) 记录 — flat 列表.

        Returns
        -------
        list[dict] — 每条 {set_id, material_id, label_id, dimension, value,
                         annotator, confidence, created_at}
        """
        try:
            conn = self._conn or get_connection()
            rows = conn.execute(
                "SELECT si.set_id, si.material_id, si.label_id, "
                "       al.dimension, al.value, al.annotator, al.confidence, al.created_at "
                "FROM admission_set_items si "
                "JOIN admission_label al ON si.label_id = al.id "
                "WHERE si.set_id = ? "
                "ORDER BY si.material_id, al.dimension",
                (set_id,),
            ).fetchall()
            return [
                {
                    "set_id": r[0],
                    "material_id": r[1],
                    "label_id": r[2],
                    "dimension": r[3],
                    "value": r[4],
                    "annotator": r[5],
                    "confidence": r[6],
                    "created_at": r[7],
                }
                for r in rows
            ]
        except sqlite3.OperationalError as e:
            logger.warning(f"admission_log tables missing: {e}")
            return []


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------
def _validate_dimensions(dimensions: dict[str, str]) -> None:
    """校验 dimensions 字典的 key/value 全部落在 ANNOTATION_DIMENSIONS 内."""
    if not dimensions:
        raise ValueError("dimensions 不能为空")
    for dim, val in dimensions.items():
        if dim not in ANNOTATION_DIMENSIONS:
            raise ValueError(
                f"未知维度 {dim!r}; 允许: {sorted(ANNOTATION_DIMENSIONS.keys())}"
            )
        allowed = ANNOTATION_DIMENSIONS[dim]
        if val not in allowed:
            raise ValueError(
                f"维度 {dim!r} 的值 {val!r} 越界; 允许: {allowed}"
            )


def _safe_json(obj: Any) -> str:
    """稳定序列化 (与 v1_evidence_service 同)."""
    import json
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
