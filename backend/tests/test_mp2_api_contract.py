"""MP-2 API 契约测试 — 候选池 HTTP 全链 + 调度 job 采集路由。

覆盖
----
- 契约链: POST /candidates → GET /candidates → approve → event_technique_map
  + audit_log_mp2_review → GET /event-types/{id}/techniques → 进度统计
- 前端契约: 候选字段名 ``id`` (b1); batch 响应 ``approved_count``/``skipped_count`` (b2)
- 异常契约: 低置信度 400 / 未知 event_type 404 / 重复 approve 409 / reject 缺 reason 400
- 调度 job: ``_mp2_ingest_all`` 对 agent_A~E 11 类的 per-agent 路由;
  ``_mp2_reports_with_candidates`` 增量过滤语义 (跳过已产候选的报告)

API 层用 ``e2e_api_client`` (隔离 temp DB, 不启 lifespan); job 层用 ``temp_db``。
"""
from __future__ import annotations

import pytest

EVENT_TYPE_ID = "evt_ransomware"


# ===========================================================================
# API 契约链 (e2e_api_client)
# ===========================================================================
def test_candidate_approve_chain_e2e(e2e_api_client):
    """候选补录 → 列表 → approve → map/audit → 技战法链 → 进度, 全链打通."""
    client = e2e_api_client

    # 1) POST /candidates — 手工补录 (脚本/修复入口)
    resp = client.post(
        "/api/event-technique/candidates",
        json={
            "event_type_id": EVENT_TYPE_ID,
            "technique_id": "T1486",
            "stage": "Impact",
            "confidence": 0.9,
            "evidence_quote": "deleted shadow copies using vssadmin",
            "source_report_id": "ir_contract_test_1",
            "agent_owner": "A",
        },
    )
    assert resp.status_code == 200, resp.text
    created = resp.json()
    assert created["owner_status"] == "pending"
    cid = created["id"]
    assert cid.startswith("etc_")

    # 2) GET /candidates — 前端字段名契约 (b1: 后端返回 "id")
    resp = client.get(
        "/api/event-technique/candidates", params={"event_type_id": EVENT_TYPE_ID}
    )
    assert resp.status_code == 200, resp.text
    listed = resp.json()
    assert listed["total"] == 1
    item = listed["items"][0]
    assert item["id"] == cid, "候选字段名必须是 'id' (前端 CandidateRow 契约)"
    assert "technique_id" in item and "confidence" in item and "stage" in item

    # 3) POST /candidates/{id}/approve → 落 map + audit
    resp = client.post(
        f"/api/event-technique/candidates/{cid}/approve",
        json={"owner": "owner", "note": "looks good"},
    )
    assert resp.status_code == 200, resp.text
    approved = resp.json()
    assert approved["candidate_id"] == cid
    assert approved["map_id"].startswith("etm_")

    # 3a) 终态落 event_technique_map
    from backend.repository.event_technique_repo import EventTechniqueMapRepo

    maps = EventTechniqueMapRepo().list_by_event_type(EVENT_TYPE_ID)
    assert any(m["id"] == approved["map_id"] and m["technique_id"] == "T1486" for m in maps)

    # 3b) 审计落 audit_log_mp2_review (actor=owner)
    from backend.repository.event_technique_repo import Mp2AuditRepo

    audits = Mp2AuditRepo().list_by_target(cid)
    assert any(a["action"] == "approve" and a["actor"] == "owner" for a in audits)

    # 4) GET /event-types/{id}/techniques — 已审定技战法链
    resp = client.get(f"/api/event-technique/event-types/{EVENT_TYPE_ID}/techniques")
    assert resp.status_code == 200, resp.text
    chain = resp.json()
    assert chain["event_type"]["id"] == EVENT_TYPE_ID
    techs = chain["techniques"]
    assert any(t["technique_id"] == "T1486" for t in techs)
    assert all("technique_name" in t for t in techs), "渲染契约: 每条技战法须带 technique_name"

    # 5) 进度: GET /event-types 内嵌 candidate_stats
    resp = client.get("/api/event-technique/event-types")
    assert resp.status_code == 200, resp.text
    row = next(i for i in resp.json()["items"] if i["id"] == EVENT_TYPE_ID)
    assert row["candidate_stats"]["approved"] == 1
    assert row["candidate_stats"]["pending"] == 0
    assert row["candidate_stats"]["approved_map"] == 1

    # 6) 状态过滤契约: approve 后不再出现在 pending 列表
    resp = client.get(
        "/api/event-technique/candidates",
        params={"event_type_id": EVENT_TYPE_ID, "owner_status": "pending"},
    )
    assert resp.json()["total"] == 0


def test_create_candidate_low_confidence_rejected(e2e_api_client):
    """confidence < CONFIDENCE_THRESHOLD (0.4) → 400 (不入候选池)."""
    resp = e2e_api_client.post(
        "/api/event-technique/candidates",
        json={
            "event_type_id": EVENT_TYPE_ID,
            "technique_id": "T1486",
            "stage": "Impact",
            "confidence": 0.2,
            "evidence_quote": "x",
            "source_report_id": "ir_low_conf",
        },
    )
    assert resp.status_code == 400, resp.text


def test_create_candidate_unknown_event_type(e2e_api_client):
    """未知 event_type_id → 404."""
    resp = e2e_api_client.post(
        "/api/event-technique/candidates",
        json={
            "event_type_id": "evt_does_not_exist",
            "technique_id": "T1486",
            "stage": "Impact",
            "confidence": 0.9,
            "evidence_quote": "x",
            "source_report_id": "ir_unknown_et",
        },
    )
    assert resp.status_code == 404, resp.text


def test_double_approve_conflict(e2e_api_client):
    """同一 candidate 二次 approve → 409 (map 已落, 防重复)."""
    client = e2e_api_client
    cid = client.post(
        "/api/event-technique/candidates",
        json={
            "event_type_id": EVENT_TYPE_ID,
            "technique_id": "T1490",
            "stage": "Impact",
            "confidence": 0.8,
            "evidence_quote": "inhibit recovery",
            "source_report_id": "ir_double_approve",
        },
    ).json()["id"]

    first = client.post(f"/api/event-technique/candidates/{cid}/approve", json={"owner": "owner"})
    assert first.status_code == 200, first.text
    second = client.post(f"/api/event-technique/candidates/{cid}/approve", json={"owner": "owner"})
    assert second.status_code == 409, second.text


def test_reject_requires_reason(e2e_api_client):
    """reject 缺 reason → 400 (审计要求); 带 reason → 200 且落审计."""
    client = e2e_api_client
    cid = client.post(
        "/api/event-technique/candidates",
        json={
            "event_type_id": EVENT_TYPE_ID,
            "technique_id": "T1489",
            "stage": "Impact",
            "confidence": 0.5,
            "evidence_quote": "stop service",
            "source_report_id": "ir_reject_test",
        },
    ).json()["id"]

    bad = client.post(
        f"/api/event-technique/candidates/{cid}/reject",
        json={"owner": "owner", "reason": ""},
    )
    assert bad.status_code == 422, bad.text  # pydantic min_length=1 先拦

    ok = client.post(
        f"/api/event-technique/candidates/{cid}/reject",
        json={"owner": "owner", "reason": "证据不足"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "rejected"

    from backend.repository.event_technique_repo import Mp2AuditRepo

    assert any(a["action"] == "reject" for a in Mp2AuditRepo().list_by_target(cid))


def test_batch_approve_response_contract(e2e_api_client):
    """batch approve 响应键 approved_count/skipped_count (b2 前端契约).

    构造 2 条 pending: 0.9 (≥ 默认 0.7 阈值 → approve) / 0.5 (< 阈值 → skip).
    """
    client = e2e_api_client
    for tid, conf in (("T1486", 0.9), ("T1490", 0.5)):
        resp = client.post(
            "/api/event-technique/candidates",
            json={
                "event_type_id": EVENT_TYPE_ID,
                "technique_id": tid,
                "stage": "Impact",
                "confidence": conf,
                "evidence_quote": "evidence",
                "source_report_id": f"ir_batch_{tid}",
            },
        )
        assert resp.status_code == 200, resp.text

    resp = client.post(
        f"/api/event-technique/event-types/{EVENT_TYPE_ID}/batch-approve",
        json={"owner": "owner"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["approved_count"] == 1
    assert body["skipped_count"] == 1
    assert body["event_type_id"] == EVENT_TYPE_ID


# ===========================================================================
# 调度 job — 采集路由 (temp_db)
# ===========================================================================
def test_mp2_ingest_all_routes_all_agents(temp_db):
    """_mp2_ingest_all 覆盖 agent_A~E 全部 11 类, per-agent 路由正确."""
    from backend.scheduler.jobs.security import _mp2_ingest_all

    mapping = _mp2_ingest_all()

    # agent_A — 每子目录一个 event_type
    for et in (
        "evt_brute_force",
        "evt_phishing_social",
        "evt_ransomware",
        "evt_supply_chain",
        "evt_web_app_intrusion",
    ):
        assert mapping.get(et) == "A", f"agent_A 路由缺失: {et}"
    # agent_B — 扁平目录, frontmatter event_type_id 分类
    for et in ("evt_ai_model_poison", "evt_cloud_misconfig", "evt_insider_threat"):
        assert mapping.get(et) == "B", f"agent_B 路由缺失: {et}"
    # agent_C/D/E — 固定 event_type
    assert mapping.get("evt_fraud") == "C"
    assert mapping.get("evt_data_breach") == "D"
    assert mapping.get("evt_regulatory_notice") == "E"
    assert len(mapping) == 11, f"应覆盖 11 类 event_type, 实得 {len(mapping)}: {mapping}"

    # 落库验证: 有 frontmatter 路径 (agent_A) 与无 frontmatter 路径 (agent_D)
    from backend.services.incident_report_service import IncidentReportService

    svc = IncidentReportService()
    assert len(svc.list_reports_by_event_type("evt_ransomware", 50)) == 5
    assert len(svc.list_reports_by_event_type("evt_data_breach", 50)) == 3


def test_mp2_incremental_filter_skips_processed_reports(temp_db):
    """_mp2_reports_with_candidates 返回已产候选的 report_id — 增量跳过语义."""
    from backend.repository.event_technique_repo import (
        EventTechniqueCandidateRepo,
        new_ulid,
    )
    from backend.scheduler.jobs.security import (
        _mp2_ingest_all,
        _mp2_reports_with_candidates,
    )
    from backend.services.incident_report_service import IncidentReportService

    _mp2_ingest_all()
    reports = IncidentReportService().list_reports_by_event_type("evt_fraud", 50)
    assert reports, "agent_C 语料应已入库"
    rid = reports[0]["id"]

    # 未产候选 → 空集 (job 会处理该报告)
    assert _mp2_reports_with_candidates("evt_fraud") == set()

    # 手工落一条候选 → 该 report 被增量过滤
    EventTechniqueCandidateRepo().insert(
        candidate_id=new_ulid("etc"),
        event_type_id="evt_fraud",
        technique_id="T1657",
        stage="Impact",
        confidence=0.8,
        evidence_quote="fraud",
        rationale=None,
        source_report_id=rid,
        llm_model="manual",
        llm_run_at="2026-09-13T00:00:00Z",
        agent_owner="C",
    )
    assert _mp2_reports_with_candidates("evt_fraud") == {rid}


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])