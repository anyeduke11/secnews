"""MP-2 抽取守卫测试 — LLM 抽取候选池的四条硬校验 (DISCUSSION §7.2 规约).

守卫矩阵
--------
- test_technique_id_valid      — 抽出的 technique_id 全部在 attack_techniques 表内 (FK)
- test_stage_in_killchain      — stage 在 event_type 的 kill_chain_stages 内
- test_evidence_quote_substring — evidence_quote 是源文子串 (normalized fuzz)
- test_confidence_threshold    — confidence ∈ [0,1], < 0.4 不入候选池 (service 层 enforce)

测试在 temp_db 隔离库跑: 加载 attack_techniques (load_attack_data) → 入库合成报告 →
跑 EventTechniqueExtractService.extract_for_report → 对产出候选逐条断言。
"""
from __future__ import annotations

import pytest

from backend.repository.db import get_connection
from backend.repository.event_technique_repo import (
    EventTechniqueCandidateRepo,
    EventTypeRepo,
)
from backend.services.attack_loader import load_attack_data
from backend.services.event_technique_extract_service import (
    CONFIDENCE_THRESHOLD,
    EventTechniqueExtractService,
    _normalize_text,
)
from backend.services.incident_report_service import IncidentReportService

EVENT_TYPE_ID = "evt_ransomware"

# 合成报告 — 含多个 typical_signals 关键词, 保证 mock 抽取有产出
REPORT_BODY = (
    "The attackers gained initial access through RDP with stolen credentials, "
    "then executed malicious commands via PowerShell. Before deploying the ransomware "
    "payload, they deleted shadow copies using vssadmin to inhibit system recovery. "
    "Sensitive data was exfiltrated over the command and control channel before "
    "encryption. The ransom note demanded payment in cryptocurrency."
)


@pytest.fixture
def extracted_env(temp_db):
    """隔离库 + attack_techniques 数据 + 1 份报告 + mock 抽取结果."""
    load_attack_data()
    et_repo = EventTypeRepo()
    assert et_repo.get(EVENT_TYPE_ID), "migration 117 未 seed evt_ransomware"

    report_svc = IncidentReportService()
    ingested = report_svc.ingest_report(
        source_url="https://example.com/guard-test-report",
        title="Guard test synthetic report",
        fetched_at="2026-09-13T00:00:00Z",
        report_md=REPORT_BODY,
        event_class_hint=EVENT_TYPE_ID,
        agent_owner="A",
    )
    svc = EventTechniqueExtractService()
    result = asyncio_run_extract(svc, ingested["id"])
    return {
        "report": report_svc.get_report(ingested["id"]),
        "result": result,
        "service": svc,
    }


def asyncio_run_extract(svc: EventTechniqueExtractService, report_id: str) -> dict:
    import asyncio

    return asyncio.run(svc.extract_for_report(report_id, EVENT_TYPE_ID, "mock-extract-v1", "A"))


def _candidates_in_db() -> list[dict]:
    return EventTechniqueCandidateRepo().list_by_event_type(EVENT_TYPE_ID)


# ---------------------------------------------------------------------------
# 守卫 1: technique_id 必须在 attack_techniques 内
# ---------------------------------------------------------------------------
def test_technique_id_valid(extracted_env):
    """抽出的 technique_id 全部在 attack_techniques 表内 (FK 守卫)."""
    conn = get_connection()
    valid = {str(r["id"]) for r in conn.execute("SELECT id FROM attack_techniques").fetchall()}
    assert valid, "attack_techniques 未落数据 — FK 校验无目标"
    candidates = _candidates_in_db()
    assert candidates, "mock 抽取应产出候选 (合成报告含典型信号)"
    bad = [c for c in candidates if c["technique_id"] not in valid]
    assert not bad, f"FK 守卫失败: {[(c['id'], c['technique_id']) for c in bad]}"


# ---------------------------------------------------------------------------
# 守卫 2: stage 在 kill_chain_stages 内
# ---------------------------------------------------------------------------
def test_stage_in_killchain(extracted_env):
    """stage 字段在 event_type 的 kill_chain_stages 列表内."""
    et = EventTypeRepo().get(EVENT_TYPE_ID)
    allowed = set(et["kill_chain_stages"])
    candidates = _candidates_in_db()
    assert candidates
    bad = [c for c in candidates if c["stage"] not in allowed]
    assert not bad, f"stage 守卫失败: {[(c['id'], c['stage']) for c in bad]}, allowed={allowed}"


# ---------------------------------------------------------------------------
# 守卫 3: evidence_quote 是源文子串
# ---------------------------------------------------------------------------
def test_evidence_quote_substring(extracted_env):
    """evidence_quote 必须是 source_report.report_md 的子串 (normalized fuzz)."""
    report_md = extracted_env["report"]["report_md"]
    norm_md = _normalize_text(report_md)
    candidates = _candidates_in_db()
    assert candidates
    bad = [c for c in candidates if _normalize_text(c["evidence_quote"]) not in norm_md]
    assert not bad, f"evidence_quote 守卫失败: {[(c['id'], c['evidence_quote'][:40]) for c in bad]}"


# ---------------------------------------------------------------------------
# 守卫 4: confidence 阈值
# ---------------------------------------------------------------------------
def test_confidence_threshold(extracted_env):
    """confidence ∈ [0,1]; < 0.4 不入候选池 (service 层 enforce + 守卫反向断言)."""
    candidates = _candidates_in_db()
    assert candidates
    for c in candidates:
        assert 0.0 <= c["confidence"] <= 1.0, f"confidence 越界: {c['id']} {c['confidence']}"
        assert c["confidence"] >= CONFIDENCE_THRESHOLD, (
            f"低于阈值的候选混入池: {c['id']} conf={c['confidence']}"
        )
    # service 层反向断言: 低置信度候选被 _validate_candidate 拒绝
    svc: EventTechniqueExtractService = extracted_env["service"]
    ok_low, reason = svc._validate_candidate(
        {
            "technique_id": "T1486",
            "stage": "Impact",
            "confidence": 0.2,
            "evidence_quote": "ransom note demanded payment",
        },
        REPORT_BODY,
        ["Initial Access", "Execution", "Impact"],
    )
    assert not ok_low and "confidence_below_threshold" in reason
