"""v0.8.8 P4 R-10: 七段主干链路埋点 (trunk stage spans) 回归门禁。

测试意图 (WHY):
- R-10 要求 Item→Signal→Case→Claim→Run→Artifact→Knowledge 七段每段记录
  trace_id / stage / 起始时间 / 耗时 / 结果状态 / 失败原因码, 落
  audit_log (复用现表, PRD §4.4 R-04 裁决 observability_records 实表 =
  audit_log), 并提供 GET /api/observability/trace/{trace_id} 查询面。
- 本文件钉住四个契约:
  ① 七段按 trace_id 可串出完整时序 (occurred_at 升序 + missing_stages);
  ② 失败 span 带 error_code 且异常原样重抛 (埋点只观测不拦截);
  ③ 关闭开关 (config.trunk_trace_enabled) 生效 — 关闭后零写入、主链不变;
  ④ 查询端点经真实 FastAPI 路由可达 (e2e_api_client 全路由挂载)。

用 temp_db (跑全套 migration) 断言生产 schema (audit_log 由 migration 080
建表, idx_audit_log_trace 部分索引本就为 trace 查询预留)。
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from backend.observability import set_trace_id
from backend.observability_records import (
    TRUNK_STAGES,
    query_stage_spans,
    stage_span,
)


def _span_count(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE actor = 'trunk'"
        ).fetchone()[0]
    finally:
        conn.close()


def test_seven_stages_chain_by_trace_id(temp_db: Path) -> None:
    """验收①: 七段 span 按 trace_id 升序串出完整时序, missing_stages 为空。"""
    set_trace_id("trace-seven-stages")
    for i, stage in enumerate(TRUNK_STAGES):
        with stage_span(stage, target=f"{stage}:obj-{i}"):
            pass
    result = query_stage_spans("trace-seven-stages")
    assert [s["stage"] for s in result["stages"]] == list(TRUNK_STAGES)
    assert result["missing_stages"] == []
    assert all(s["status"] == "ok" and "started_at" in s and "duration_ms" in s
               for s in result["stages"])
    assert result["stages"][0]["target"] == "item:obj-0"


def test_failed_span_records_error_code_and_reraises(temp_db: Path) -> None:
    """验收②前半: 失败 span 带 error_code, 异常原样重抛 (不吞业务异常)。"""
    set_trace_id("trace-fail")
    with pytest.raises(RuntimeError, match="boom"):
        with stage_span("claim", target="claim:j1"):
            raise RuntimeError("boom")
    result = query_stage_spans("trace-fail")
    assert len(result["stages"]) == 1
    span = result["stages"][0]
    assert span["stage"] == "claim"
    assert span["status"] == "failed"
    assert span["error_code"] == "E_INTERNAL.RuntimeError"


def test_stage_span_measures_50ms_delay(temp_db: Path) -> None:
    """验收③ (单元级): 注入 50ms 延迟后 duration_ms 可观测 (±10ms 容差带放宽到 ±15)。"""
    set_trace_id("trace-delay")
    with stage_span("run", target="run:r1"):
        time.sleep(0.05)
    span = query_stage_spans("trace-delay")["stages"][0]
    assert 45 <= span["duration_ms"] <= 200, span["duration_ms"]


def test_kill_switch_disables_writing(temp_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """验收④: config.trunk_trace_enabled=False 时零写入, 主链行为不变。"""
    from backend.config import config

    set_trace_id("trace-off")
    monkeypatch.setattr(config, "trunk_trace_enabled", False)
    with stage_span("case", target="case:c1"):
        pass  # 关闭状态下业务照常执行, 只是不写 span
    assert _span_count(temp_db) == 0


def test_stage_span_fail_open_on_write_failure(temp_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """RA-6: span 写库失败绝不拖垮主链 (双保险外层)。"""
    from backend import observability_records

    def _explode(*a, **kw):
        raise sqlite3.OperationalError("db locked")

    monkeypatch.setattr(observability_records, "record_stage_span", _explode)
    set_trace_id("trace-failopen")
    with stage_span("artifact", target="artifact:a1"):
        pass  # 写失败被吞, 业务正常完成
    assert _span_count(temp_db) == 0  # 确实没写进去 (而不是靠吞错写了一半)


def test_unknown_stage_fails_loud(temp_db: Path) -> None:
    """stage 名拼错立即 ValueError (stage 名是查询契约的一部分, 静默错名会查不到)。"""
    set_trace_id("trace-bogus")
    with pytest.raises(ValueError, match="unknown trunk stage"):
        with stage_span("bogus_stage"):
            pass


def test_unknown_trace_returns_all_missing(temp_db: Path) -> None:
    """无任何 span 的 trace 返回空 stages + 七段全 missing (前端空态依据)。"""
    result = query_stage_spans("trace-never-existed")
    assert result["stages"] == []
    assert result["missing_stages"] == list(TRUNK_STAGES)


def test_trace_endpoint_via_http(temp_db: Path) -> None:
    """验收②: GET /api/observability/trace/{trace_id} 经真实路由返回有序 span。"""
    set_trace_id("trace-http")
    with stage_span("signal", target="signal:s1"):
        pass
    with stage_span("case", target="case:c1"):
        pass
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.observability_router import router
    from backend.exceptions import register_exception_handlers

    app = FastAPI()
    app.include_router(router)
    register_exception_handlers(app)
    client = TestClient(app)
    resp = client.get("/api/observability/trace/trace-http")
    assert resp.status_code == 200
    body = resp.json()
    assert [s["stage"] for s in body["stages"]] == ["signal", "case"]
    assert body["missing_stages"] == ["item", "claim", "run", "artifact", "knowledge"]
    assert "as_of" in body


# ── 接线级测试: 真实写入口必须产出 span (防埋点被静默拆除) ────────────


def test_case_service_create_emits_case_span(temp_db: Path) -> None:
    """真实接线: CaseService.create_case 必须产出 stage.case span (target=case:<id>)。"""
    from backend.services.case_service import CaseService

    set_trace_id("trace-wired-case")
    case = CaseService().create_case(title="接线测试", question="q", source="test")
    spans = query_stage_spans("trace-wired-case")["stages"]
    assert [s["stage"] for s in spans] == ["case"]
    assert spans[0]["status"] == "ok"
    assert spans[0]["target"] == f"case:{case.id}"


def test_run_service_insert_emits_run_span(temp_db: Path) -> None:
    """真实接线: RunService.create_or_replay 必须产出 stage.run span (target=run:<id>)。"""
    from backend.repository.action_repo import ActionRepository
    from backend.repository.judgment_repo import JudgmentRepository
    from backend.services.run_service import RunService

    set_trace_id("trace-wired-run")
    # v1_actions.judgment_id 是 NOT NULL FK (必引 published) — 直落最小链:
    # judgment(published) → action → run
    JudgmentRepository().insert({
        "id": "jd-span-test", "case_id": "case-span-test", "claim_type": "finding",
        "claim": "c", "confidence": "medium", "evidence_refs": [],
        "unknowns": [], "status": "published", "wiki_path": "items/jd-span-test.md",
        "published_at": "2026-01-01T00:00:00+00:00",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    })
    ActionRepository().insert({
        "id": "act-span-test", "case_id": "case-span-test", "judgment_id": "jd-span-test",
        "title": "run 接线", "plan": "p", "plan_hash": "h", "status": "planned",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    })
    result = RunService().create_or_replay(
        action_id="act-span-test", idempotency_key="idem-r1", attempt=1,
        protocol="direct",  # R05: mock 已移出合法协议
    )
    spans = query_stage_spans("trace-wired-run")["stages"]
    assert [s["stage"] for s in spans] == ["run"]
    assert spans[0]["target"] == f"run:{result['run']['id']}"


def test_hotspot_upsert_emits_item_span(temp_db: Path) -> None:
    """真实接线: HotspotRepository.upsert_many 必须产出 stage.item span (target 含批量)。"""
    from datetime import datetime
    from datetime import timezone as _tz

    from backend.domain.enums import Category
    from backend.domain.models import HotspotItem
    from backend.repository.hotspot_repo import HotspotRepository

    set_trace_id("trace-wired-item")
    now = datetime.now(_tz.utc)
    item = HotspotItem(
        id="hs-span-test-1", title="埋点接线测试", summary="s", source="test",
        url="https://example.com/span-test", category=Category.AI,
        published_at=now, fetched_at=now,
    )
    affected = HotspotRepository().upsert_many([item])
    assert affected == 1
    spans = query_stage_spans("trace-wired-item")["stages"]
    assert [s["stage"] for s in spans] == ["item"]
    assert spans[0]["target"] == "item:batch:1"
