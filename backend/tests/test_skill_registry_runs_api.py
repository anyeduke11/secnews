"""skill_registry_runs_api — v0.8 Phase B Task B6 集成测试 (15 case).

覆盖:
- 运行历史: 空列表 / created_at 倒序 / limit 截断 / limit 越界 422 / 未知 skill 404
- 单次回放: inputs/result/metrics JSON 反序列化 / 未知 run 404 (RUN_NOT_FOUND)
- 反馈打分: 👍=5 与 👎=1 落库回读 / 未知 run 404 / score 越界 400 FEEDBACK_INVALID /
  score 非整数 422 (pydantic)
- 验收链路 (plan §B6): 点 👍 反馈写 feedback_log → agent_memory.recall 命中
  且 hit.score join 到反馈均分
- 注册门控: gate off → runs 路由不注册 / gate on → 注册

测试策略 (与 test_skill_registry_api 同款): 自建小 FastAPI 只挂本 router —
不走 conftest e2e_api_client (其 HOTSPOT_FEATURE_GATES env 未含 skill_registry
→ gate 读 TOML false → register_routers 不挂载); DB 走 temp_db (migration 091
skill_runs + 093 feedback_log 全 schema); 父 gate True 路径 monkeypatch gate
模块 is_extension_enabled。
"""
from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.repository.db import get_connection
from backend.services.agent_memory import agent_memory


RUN_ID = "run-b6-0001"
SKILL_ID = "source-health-scan"


def _seed_run(
    run_id: str = RUN_ID,
    skill_id: str = SKILL_ID,
    *,
    created_at: str = "2026-09-01 10:00:00",
    status: str = "succeeded",
    inputs: dict | list | None = None,
    result: dict | list | None = None,
    metrics: dict | None = None,
    error: str | None = None,
) -> None:
    """直插 skill_runs 一行 — 显式 created_at 保证倒序断言确定性。"""
    get_connection().execute(
        """
        INSERT INTO skill_runs(
            run_id, ticket_id, skill_id, status, phase,
            inputs, result, metrics, error, created_at, finished_at
        ) VALUES (?, NULL, ?, ?, 'done', ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id, skill_id, status,
            json.dumps(inputs, ensure_ascii=False) if inputs is not None else None,
            json.dumps(result, ensure_ascii=False) if result is not None else None,
            json.dumps(metrics, ensure_ascii=False) if metrics is not None else None,
            error, created_at,
            created_at if status != "running" else None,
        ),
    )


@pytest.fixture()
def client(temp_db, monkeypatch):
    """小 app 只挂 runs router; 父 gate 强制 True (True 路径基线)。"""
    monkeypatch.setattr(
        "backend.services.skill_registry.gate.is_extension_enabled",
        lambda name: True,
    )
    from backend.api.skill_registry_runs_api import router

    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as c:
        yield c


# ===========================================================================
# 1. 运行历史 GET /{skill_id}/runs
# ===========================================================================
def test_list_runs_empty(client):
    """skill 存在但无运行记录 → 空数组 (非 404, 与「skill 不存在」区分)。"""
    r = client.get(f"/api/skill-registry/{SKILL_ID}/runs")
    assert r.status_code == 200
    assert r.json() == []


def test_list_runs_desc_order(client):
    """倒序: created_at DESC — 最近一次执行排最前 (RunHistory 直接消费)。"""
    for i, ts in enumerate(
        ["2026-09-01 10:00:00", "2026-09-03 12:00:00", "2026-09-02 08:00:00"]
    ):
        _seed_run(f"run-{i}", created_at=ts)
    ids = [r["run_id"] for r in client.get(f"/api/skill-registry/{SKILL_ID}/runs").json()]
    assert ids == ["run-1", "run-2", "run-0"]


def test_list_runs_unknown_skill_404(client):
    """未知 skill_id → 404 信封三字段 (P3-2), 与 A3 主路由同码 SKILL_NOT_FOUND。"""
    r = client.get("/api/skill-registry/no-such-skill/runs")
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert detail["code"] == "SKILL_NOT_FOUND"
    assert {"message", "code", "hint"} <= set(detail.keys())


def test_list_runs_limit_truncates(client):
    """limit=2 → 只回最近 2 条 (默认 20, 上限 100)。"""
    for i in range(5):
        _seed_run(f"run-{i}", created_at=f"2026-09-0{i + 1} 10:00:00")
    rows = client.get(
        f"/api/skill-registry/{SKILL_ID}/runs", params={"limit": 2}
    ).json()
    assert [r["run_id"] for r in rows] == ["run-4", "run-3"]


def test_list_runs_limit_bounds_422(client):
    """limit=0 / 101 → pydantic Query 校验 422 (ge=1, le=100)。"""
    assert client.get(
        f"/api/skill-registry/{SKILL_ID}/runs", params={"limit": 0}
    ).status_code == 422
    assert client.get(
        f"/api/skill-registry/{SKILL_ID}/runs", params={"limit": 101}
    ).status_code == 422


# ===========================================================================
# 2. 单次回放 GET /runs/{run_id}
# ===========================================================================
def test_get_run_deserializes_json(client):
    """inputs/result/metrics 存的是 JSON TEXT → 读路径反序列化为结构化对象。"""
    _seed_run(
        inputs={"query": "collector failures"},
        result={"summary": "2 failures", "items": ["hn", "reddit"]},
        metrics={"elapsed_ms": 42, "fast_path": True},
    )
    row = client.get(f"/api/skill-registry/runs/{RUN_ID}").json()
    assert row["inputs"] == {"query": "collector failures"}
    assert row["result"]["items"] == ["hn", "reddit"]
    assert row["metrics"]["fast_path"] is True
    assert row["status"] == "succeeded"


def test_get_run_unknown_404(client):
    """未知 run_id → 404 RUN_NOT_FOUND (回放入口的缺省防护)。"""
    r = client.get("/api/skill-registry/runs/no-such-run")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "RUN_NOT_FOUND"


# ===========================================================================
# 3. 反馈打分 POST /runs/{run_id}/feedback
# ===========================================================================
def test_feedback_up_score5(client):
    """👍=5 落库 — 返回完整反馈行 (含 run/skill 冗余), 回读一致。"""
    _seed_run()
    r = client.post(
        f"/api/skill-registry/runs/{RUN_ID}/feedback",
        json={"score": 5, "comment": "结果准确"},
    )
    assert r.status_code == 200
    row = r.json()
    assert row["score"] == 5
    assert row["skill_run_id"] == RUN_ID
    assert row["skill_id"] == SKILL_ID
    assert row["comment"] == "结果准确"
    stored = agent_memory.list_feedback(SKILL_ID)
    assert len(stored) == 1 and stored[0]["score"] == 5


def test_feedback_down_score1(client):
    """👎=1 同链路 (score 下界, 与 👍 上界合成 1-5 全区间两端验证)。"""
    _seed_run()
    r = client.post(f"/api/skill-registry/runs/{RUN_ID}/feedback", json={"score": 1})
    assert r.status_code == 200
    assert r.json()["score"] == 1


def test_feedback_unknown_run_404(client):
    """孤儿反馈拒绝: run 不存在 → 404 RUN_NOT_FOUND (先于 score 校验)。"""
    r = client.post(
        "/api/skill-registry/runs/no-such-run/feedback", json={"score": 5}
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "RUN_NOT_FOUND"


def test_feedback_score_out_of_range_400(client):
    """score=0 / 6 → record_feedback ValueError → 400 FEEDBACK_INVALID。"""
    _seed_run()
    for bad in (0, 6):
        r = client.post(
            f"/api/skill-registry/runs/{RUN_ID}/feedback", json={"score": bad}
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "FEEDBACK_INVALID"
    assert agent_memory.list_feedback(SKILL_ID) == []


def test_feedback_score_float_422(client):
    """score=3.5 → pydantic int 类型拒绝 422 (不落库)。"""
    _seed_run()
    r = client.post(
        f"/api/skill-registry/runs/{RUN_ID}/feedback", json={"score": 3.5}
    )
    assert r.status_code == 422
    assert agent_memory.list_feedback(SKILL_ID) == []


def test_feedback_recall_acceptance(client):
    """B6 验收链路: 👍 反馈写 feedback_log → recall 命中且 hit.score=反馈分。

    plan 验收原文「点 👍/👎 反馈写 agent_memory, recall API 可命中」—
    skill_id 出现在 intent 文本触发 exact 路径, _attach_feedback_scores 把
    feedback_log 均分 join 进 hit.score, 证明反馈已可被后续执行感知。
    """
    _seed_run(
        skill_id="weekly-top-events",
        inputs={"intent": "生成上周安全事件周报"},
    )
    r = client.post(
        "/api/skill-registry/runs/run-b6-0001/feedback",
        json={"score": 5, "comment": "top5 选择准确"},
    )
    assert r.status_code == 200
    hits = agent_memory.recall("weekly-top-events 生成上周安全事件周报", k=5)
    assert hits, "recall 必须命中已反馈的 run"
    hit = next(h for h in hits if h.skill_run_id == "run-b6-0001")
    assert hit.score == 5.0
    assert hit.match_path == "exact"


# ===========================================================================
# 4. 注册门控 (gate off → runs 路由不注册)
# ===========================================================================
def _build_app_with_gate(monkeypatch, on: bool) -> FastAPI:
    """按 test_skill_registry_api 同款: patch _load_gates 后真实注册。"""
    import backend.extensions as extensions
    from backend.api import register_routers

    monkeypatch.setattr(extensions, "_load_gates", lambda: {"skill_registry": on})
    app = FastAPI()
    register_routers(app)
    return app


def _paths(app: FastAPI) -> set[str]:
    """递归收集注册路径 (含 _IncludedRouter 嵌套 — A3 同款 helper)。"""
    paths: set[str] = set()
    stack = list(app.routes)
    while stack:
        r = stack.pop()
        path = getattr(r, "path", None)
        if path:
            paths.add(path)
            continue
        router = getattr(r, "original_router", None) or getattr(r, "router", None)
        if router is not None:
            stack.extend(router.routes)
    return paths


def test_gate_off_runs_routes_not_registered(monkeypatch, temp_db):
    """gate off → /api/skill-registry/runs* 不可达 (fail-closed)。"""
    app = _build_app_with_gate(monkeypatch, on=False)
    assert not any("/runs" in p for p in _paths(app) if p.startswith("/api/skill-registry"))
    with TestClient(app) as c:
        assert c.get("/api/skill-registry/runs/whatever").status_code == 404


def test_gate_on_runs_routes_registered(monkeypatch, temp_db):
    """gate on → runs 三路由随主路由一起注册 (同 gate 同生)。"""
    app = _build_app_with_gate(monkeypatch, on=True)
    paths = _paths(app)
    assert "/api/skill-registry/runs/{run_id}" in paths
    assert "/api/skill-registry/{skill_id}/runs" in paths
    assert "/api/skill-registry/runs/{run_id}/feedback" in paths
