"""v1 采集桥 — D1「点火」: 真实源 RSS → SourcePipeline → 准入 → v1_materials + v1_signals.

v0.8.5 D1 (spec docs/v0.8.5/V0.8.5_PLAN.md §11). T06/T07/T05 全是现成件, 本文件只做编排:

  job (300s) → 选源 (crawler_sources, env HOTSPOT_V1_INTAKE_SOURCES, 默认 security:SecWiki)
  → 预取 RSS (SSRF 校验 + feedparser; 失败三态映射 FetchOutcome)
  → SourcePipeline.run (T06 原样: lease/watermark/幂等/仅 committed>0 才推进水位)
  → on_item 回调收集 (body, committed|idempotent|failed)
  → V1AdmissionService.evaluate (info_filter rules; deny → quarantine, 不产信号)
  → allow/neutral → ensure_source_subject → signal create_intent/commit

幂等设计 (重复抓取是 RSS 常态, 必须全部走 IdempotentReplay 而非主键冲突):
  - FetchRequest.cursor 恒 None → request body 稳定 → 管线内 item submission_key 跨窗口稳定
  - material id = "mat"+sha256(link|title)[:24] (内容寻址, 跨窗口不变)
  - subject: 每源一个, key/body 均稳定 (不含时间戳字段)
  - signal key = "v1-signal-{material_id}" (材料重放时信号自动重试, 不重复)
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
from datetime import datetime, timezone
from typing import Any

from backend.logging_config import logger
from backend.repository.db import get_connection
from backend.services.source_pipeline import (
    FetchOutcome,
    FetchRequest,
    SourceLease,
    SourcePipeline,
    SourceWatermark,
)

_DEFAULT_SOURCES = "security:SecWiki"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_source_ids() -> list[str]:
    raw = os.environ.get("HOTSPOT_V1_INTAKE_SOURCES", _DEFAULT_SOURCES)
    return [s.strip() for s in raw.split(",") if s.strip()]


class V1IngestBridge:
    """单源点火编排: RSS → SourcePipeline → 准入 → material+signal."""

    def __init__(
        self,
        source: dict[str, Any],
        *,
        rules: list[dict[str, Any]] | None = None,
        max_items: int = 30,
        lease: SourceLease | None = None,
        watermark: SourceWatermark | None = None,
    ) -> None:
        self.source = source
        self.source_id = source["id"]
        self.source_name = source.get("name", self.source_id)
        self.feed_url = source.get("feed_url") or source.get("url") or ""
        self.rules = rules
        self.max_items = max_items
        self.pipeline = SourcePipeline(
            lease=lease or SourceLease(ttl_sec=120),
            watermark=watermark or SourceWatermark(),
            evidence_service=self._make_evidence(),
        )
        self.collected: list[tuple[dict[str, Any], str]] = []

    # -- 现成件装配 --------------------------------------------------------
    def _make_evidence(self):
        from backend.services.v1_evidence_service import V1EvidenceService
        return V1EvidenceService(projection_dir=None)  # D1: 信号/Material 只入库, 不落 wiki

    def _make_admission(self):
        from backend.services.v1_admission_service import V1AdmissionService
        return V1AdmissionService()

    # -- fetch (预取, 同步注入 pipeline) ------------------------------------
    async def _fetch_rss(self) -> tuple[FetchOutcome, list[dict[str, Any]], str | None]:
        """SSRF 校验 + feedparser (to_thread). 三态: ERROR / NOT_MODIFIED(空 feed) / SUCCESS."""
        from backend.utils.url_safety import UrlSafetyError, validate_url

        try:
            validate_url(self.feed_url)
        except UrlSafetyError as e:
            logger.warning(f"v1-intake ssrf block: {self.source_id} → {str(e)[:80]}")
            return FetchOutcome.ERROR, [], None

        def _parse() -> dict[str, Any]:
            import feedparser  # type: ignore
            return feedparser.parse(self.feed_url)

        try:
            d = await asyncio.to_thread(_parse)
        except Exception as e:
            logger.warning(f"v1-intake fetch crash: {self.source_id} {type(e).__name__}: {str(e)[:60]}")
            return FetchOutcome.ERROR, [], None

        status = d.get("status")
        entries = d.get("entries", []) or []
        if status is not None and status >= 400:
            logger.warning(f"v1-intake http {status}: {self.source_id}")
            return FetchOutcome.ERROR, [], None
        if not entries:
            return FetchOutcome.NOT_MODIFIED, [], None

        # next_cursor = feed etag 优先, 否则最新 entry 指纹 (feed 未变则稳定)
        cursor = d.get("etag") or _sha("|".join(
            (e.get("link") or "") + (e.get("title") or "") for e in entries[:5]
        ))[:16]
        return FetchOutcome.SUCCESS, entries[: self.max_items], cursor

    # -- parse (entry → material body; 附带准入辅助字段) ---------------------
    _PLACEHOLDER_MARKERS = ("暂未更新", "更多最新文章")  # SecWiki 占位条目 (非真实情报)
    _TAG_STRIP = re.compile(r"<[^>]+>")

    def _parse_entry(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        title = self._TAG_STRIP.sub("", (entry.get("title") or "")).strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            return None  # 非 fatal, 管线按 skip 计
        if any(m in title for m in self._PLACEHOLDER_MARKERS):
            return None  # feed 卫生: 占位/导航条目不是情报
        summary = self._TAG_STRIP.sub(" ", (entry.get("summary") or "")).strip()[:400]
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        published_at = (
            datetime(*published[:6], tzinfo=timezone.utc).isoformat()
            if published else _now_iso()
        )
        mat_id = "mat" + _sha(f"{link}|{title}")[:24]
        # 注意: body 必须跨 run 逐字节稳定 (create_intent 以 body_hash 判 IdempotentReplay)
        # — 时间戳字段 (fetched_at) 不入 body, 首次 INSERT 由表 default 兜底
        return {
            # v1_materials 契约字段
            "id": mat_id,
            "source_kind": "url",
            "url": link,
            "title": title,
            "content_hash": _sha(f"{title}|{link}|{summary}"),
            "content_length": len(title) + len(summary),
            "summary": summary,
            "published_at": published_at,
            "fetched_by": f"v1-intake:{self.source_id}",
            # 准入辅助字段 (admission.evaluate 约定)
            "category": self.source.get("category", "unknown"),
            "source_name": self.source_name,
            "source_id": self.source_id,
        }

    # -- subject / signal ---------------------------------------------------
    def _subject_body(self) -> dict[str, Any]:
        # body 不含时间戳 → 跨 run hash 稳定 → IdempotentReplay
        return {
            "id": "subj-src-" + _sha(self.source_id)[:24],
            "entity_type": "other",
            "canonical_name": f"信源: {self.source_name}",
        }

    def _ensure_source_subject(self, evidence) -> str:
        from backend.services.v1_evidence_service import IdempotentReplay
        body = self._subject_body()
        key = "v1-subject-src-" + _sha(self.source_id)[:16]
        try:
            intent = evidence.create_intent(key, "subject", body, submitted_by="v1-intake")
            evidence.commit_intent(intent["intent_id"], entity_id=body["id"])
        except IdempotentReplay:
            pass  # subject 已存在 — 正常路径
        return body["id"]

    def _commit_signal(self, evidence, subject_id: str, mat: dict[str, Any], reason: str, rule_version: str) -> str:
        from backend.services.v1_evidence_service import IdempotentReplay
        sig_id = "sig" + _sha(mat["id"])[:24]
        body = {
            "id": sig_id,
            "subject_id": subject_id,
            "material_id": mat["id"],
            "summary": mat.get("summary") or mat.get("title", ""),
            "occurred_at": mat.get("published_at") or mat.get("fetched_at") or _now_iso(),
            "admission_rule_version": rule_version,
            "admission_reason": reason[:200],
            "confidence": "unverified",
            "status": "unverified",
        }
        try:
            intent = evidence.create_intent(f"v1-signal-{mat['id']}", "signal", body, submitted_by="v1-intake")
            evidence.commit_intent(intent["intent_id"], entity_id=sig_id)
            return "committed"
        except IdempotentReplay:
            return "idempotent"

    # -- 主入口 --------------------------------------------------------------
    async def run(self) -> dict[str, Any]:
        """单源一次点火: fetch → pipeline(material) → 准入 → signal."""
        outcome, raw_items, next_cursor = await self._fetch_rss()
        request = FetchRequest(source_id=self.source_id, cursor=None, requester="v1-intake")

        def _sync_run() -> Any:
            return self.pipeline.run(
                request,
                fetch_fn=lambda req: (outcome, raw_items, next_cursor),
                parse_fn=self._parse_entry,
                on_item=lambda body, status: self.collected.append((body, status)),
            )

        result = await asyncio.to_thread(_sync_run)

        summary: dict[str, Any] = {
            "source_id": self.source_id,
            "outcome": result.outcome.value,
            "items_parsed": result.items_parsed,
            "materials_committed": result.items_committed,
            "materials_idempotent": result.items_idempotent,
            "materials_failed": result.items_failed,
            "signals_committed": 0,
            "signals_idempotent": 0,
            "signals_denied": 0,
            "denied_sample": [],
            "error": result.error,
        }
        eligible = [b for b, st in self.collected if st in ("committed", "idempotent")]
        if not eligible:
            return summary

        admission = self._make_admission()
        rules_version = "info-filter:default"
        try:
            conn = get_connection()
            from backend.services.info_filter_service import list_rules
            rules = list_rules(conn, enabled_only=True)
            if rules:
                rules_version = f"info-filter@{_sha(json_rules(rules))[:8]}"
        except Exception as e:  # 规则加载失败 → None = neutral 全放行, 不阻断点火
            logger.warning(f"v1-intake rules load failed (neutral 放行): {e}")
            rules = None

        subject_id = self._ensure_source_subject(self.pipeline.evidence)
        for mat in eligible:
            result_adm = admission.evaluate(mat, rules=rules)
            # 准入日志: 全部 verdict (allow/neutral/deny) 都落 admission_log — D1 准入语义
            admission.quarantine(result_adm, mat)
            if result_adm.verdict.value == "deny":
                summary["signals_denied"] += 1
                if len(summary["denied_sample"]) < 3:
                    summary["denied_sample"].append(mat["id"])
                continue
            status = self._commit_signal(
                self.pipeline.evidence, subject_id, mat,
                reason=result_adm.reason, rule_version=rules_version,
            )
            summary[f"signals_{status}"] = summary.get(f"signals_{status}", 0) + 1
        summary["subject_id"] = subject_id
        return summary


def json_rules(rules: list[dict[str, Any]]) -> str:
    import json
    return json.dumps(rules, sort_keys=True, ensure_ascii=False)


async def run_intake_tick(source_ids: list[str] | None = None) -> dict[str, Any]:
    """一轮点火 tick: 对配置的全部源各跑一次 V1IngestBridge.

    Returns
    -------
    {"sources_run", "sources_skipped", "totals", "results"} — job 侧只 log 不抛.
    """
    ids = source_ids or _resolve_source_ids()
    conn = get_connection()
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT id, name, category, kind, url, feed_url FROM crawler_sources "
        f"WHERE enabled = 1 AND id IN ({placeholders})",
        ids,
    ).fetchall()
    found = {r["id"]: dict(r) for r in rows}

    results: list[dict[str, Any]] = []
    totals = {"materials_committed": 0, "signals_committed": 0, "signals_denied": 0}
    for sid in ids:
        src = found.get(sid)
        if not src or not (src.get("feed_url") or src.get("url")):
            results.append({"source_id": sid, "outcome": "skipped", "error": "源不存在/未启用/无 feed_url"})
            continue
        try:
            bridge = V1IngestBridge(src)
            r = await bridge.run()
            results.append(r)
            for k in totals:
                totals[k] += r.get(k, 0)
        except Exception as e:  # 单源失败不阻断其他源
            logger.error(f"v1-intake source failed: {sid} {type(e).__name__}: {str(e)[:80]}")
            results.append({"source_id": sid, "outcome": "error", "error": str(e)[:120]})
    return {
        "sources_run": sum(1 for r in results if r.get("outcome") not in ("skipped", "error")),
        "sources_skipped": sum(1 for r in results if r.get("outcome") in ("skipped", "error")),
        "totals": totals,
        "results": results,
    }
