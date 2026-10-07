"""P3-C KPI 口径切换测试 (DEV-0289).

口径裁决: 转化率带退场, 主指标 = triage_latency (signal→case P50/P90) +
artifact_yield (done 且有产物 / done); signals_ratio 降级参考值。
"""
from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.kpi_api import router as kpi_router
from backend.repository.db import get_connection
from backend.services.kpi_service import KpiService


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(kpi_router)
    return TestClient(app)


def _seed_parents() -> None:
    """种 FK 父行: subject + material + action (signals/runs 的外键依赖)。"""
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO v1_subjects (id, entity_type, canonical_name, "
        "first_seen_at, last_seen_at, revision, created_at, updated_at) "
        "VALUES ('SUBJKPI000000000000000001', 'other', 'KPI 测试主体', "
        "datetime('now'), datetime('now'), 1, datetime('now'), datetime('now'))"
    )
    conn.execute(
        "INSERT OR IGNORE INTO v1_materials (id, source_kind, url, title, content_hash, "
        "content_length, fetched_at, created_at, updated_at) "
        "VALUES ('MATKPI000000000000000001', 'url', 'https://x/kpi', 'T', 'k' * 64, "
        "100, datetime('now'), datetime('now'), datetime('now'))"
    )
    conn.execute(
        "INSERT OR IGNORE INTO v1_actions (id, case_id, judgment_id, title, plan, "
        "plan_hash, expected_artifacts_json, status, revision, created_at, updated_at) "
        "VALUES ('ACTKPI0000000000000000001', 'CASEKPI000000000000000001', "
        "'J', 't', '# p', 'h' * 64, '[]', 'planned', 1, datetime('now'), datetime('now'))"
    )
    conn.commit()


def _seed_case_with_signal(signal_created: str, lag_seconds: int, case_id: str = "CASEKPI000000000000000001") -> None:
    """种 1 信号 + 1 关联 case (时延 = lag_seconds); 信号 id 从 case_id 派生保证独立。"""
    _seed_parents()
    conn = get_connection()
    from datetime import datetime, timedelta

    t0 = datetime.strptime(signal_created, "%Y-%m-%dT%H:%M:%S")
    t1 = t0 + timedelta(seconds=lag_seconds)
    sig_id = "SIG" + case_id[3:26]  # 与 case 一一对应 (避免共享信号污染时延样本)
    conn.execute(
        "INSERT OR IGNORE INTO v1_signals (id, subject_id, material_id, summary, "
        "occurred_at, admission_rule_version, admission_reason, confidence, status, "
        "revision, created_at, updated_at) "
        "VALUES (?, 'SUBJKPI000000000000000001', 'MATKPI000000000000000001', 's', "
        "?, 'v', 'test', 'unverified', 'unverified', 1, ?, ?)",
        (sig_id, signal_created, signal_created, signal_created),
    )
    conn.execute(
        "INSERT OR IGNORE INTO v1_cases (id, title, question, revision, created_at, updated_at, "
        "tags_json, related_subject_ids_json, related_signal_ids_json, related_case_ids_json) "
        "VALUES (?, 'T', 'Q', 1, ?, ?, '[]', '[]', ?, '[]')",
        (case_id, t1.strftime("%Y-%m-%dT%H:%M:%S"), t1.strftime("%Y-%m-%dT%H:%M:%S"),
         json.dumps([sig_id])),
    )
    conn.commit()


def test_triage_latency_p50(temp_db) -> None:
    """种 2 样本 (lag 60s / 600s, 各自独立信号) → P50 介于其间且 samples=2。"""
    _seed_case_with_signal("2026-10-07T08:00:00", 60, "CASEKPI000000000000000001")
    _seed_case_with_signal("2026-10-07T09:00:00", 600, "CASEKPI000000000000000002")
    out = KpiService().triage_latency(days=30)
    assert out["samples"] == 2 and out["cases_total"] == 2
    assert out["p50_seconds"] is not None
    assert 60 <= out["p50_seconds"] <= 600
    assert out["min_seconds"] == 60.0 and out["max_seconds"] == 600.0


def test_triage_latency_case_without_signal_skipped(temp_db) -> None:
    """无关联信号的 case 不计入样本 (时延不可定义, 诚实缺省)。"""
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO v1_cases (id, title, question, revision, created_at, updated_at, "
        "tags_json, related_subject_ids_json, related_signal_ids_json, related_case_ids_json) "
        "VALUES ('CASEKPI000000000000000003', 'T', 'Q', 1, datetime('now'), datetime('now'), "
        "'[]', '[]', '[]', '[]')"
    )
    conn.commit()
    out = KpiService().triage_latency(days=30)
    assert out["cases_total"] == 1 and out["samples"] == 0
    assert out["p50_seconds"] is None


def test_artifact_yield_ratio(temp_db) -> None:
    """3 runs done (2 有产物 1 无) → yield 0.6667; 非 done 不计入分母。"""
    conn = get_connection()
    now = "datetime('now')"
    rows = [
        ("RUNKPIYIELDA00000000000001", "'[\"ART1\"]'"),
        ("RUNKPIYIELD B000000000000002".replace(" ", ""), "'[\"ART2\"]'"),
        ("RUNKPIYIELDC0000000000000003", "'[]'"),
        ("RUNKPIYIELDD0000000000000004", None),  # status=failed 不计入
    ]
    for i, (rid, arts) in enumerate(rows):
        status = "done" if i < 3 else "failed"
        conn.execute(
            f"INSERT OR IGNORE INTO v1_runs (id, action_id, attempt, protocol, "
            f"trigger_source, idempotency_key, status, "
            f"artifact_ids_json, revision, created_at, updated_at) "
            f"VALUES (?, 'ACTKPI0000000000000000001', ?, 'mcp', 'manual', ?, '{status}', "
            f"{arts if arts else 'NULL'}, 1, {now}, {now})",
            (rid, i + 1, f"idem-{rid}"),  # attempt 递增避 UNIQUE(action_id, attempt)
        )
    conn.commit()
    out = KpiService().artifact_yield(days=7)
    assert out["runs_done"] == 3 and out["runs_with_artifact"] == 2
    assert out["yield_ratio"] == 0.6667


def test_kpi_endpoint_contract(temp_db) -> None:
    """GET /api/ops/kpi → 三块结构齐 + signals_ratio 带降级注记。"""
    c = _client()
    r = c.get("/api/ops/kpi")
    assert r.status_code == 200
    d = r.json()
    assert "triage_latency" in d and "artifact_yield" in d
    ref = d["signals_ratio_reference"]
    assert "降级参考值" in ref["note"]
    assert d["triage_latency"]["window_days"] == 30
    assert d["artifact_yield"]["window_days"] == 7


def test_signals_ratio_reference_math(temp_db) -> None:
    _seed_parents()
    conn = get_connection()
    conn.execute(
        "INSERT INTO hotspots (id, title, summary, source, url, category, "
        "published_at, fetched_at, ingested_at) "
        "VALUES ('hs_kpi_1', 't', 's', 'src', 'https://x/1', 'ai', "
        "datetime('now'), datetime('now'), datetime('now'))"
    )
    conn.execute(
        "INSERT OR IGNORE INTO v1_signals (id, subject_id, material_id, summary, "
        "occurred_at, admission_rule_version, admission_reason, confidence, status, "
        "revision, created_at, updated_at) "
        "VALUES ('sig_kpi_1', 'SUBJKPI000000000000000001', 'MATKPI000000000000000001', "
        "'s', datetime('now'), 'v', 'test', 'unverified', 'unverified', 1, "
        "datetime('now'), datetime('now'))"
    )
    conn.commit()
    out = KpiService().signals_ratio(days=7)
    assert out["signals"] >= 1 and out["hotspots"] >= 1
    assert out["ratio"] is not None and out["ratio"] > 0
