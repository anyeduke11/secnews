"""v0.8.6 P2 两层质量规则 (专家规则 + AI 语义规则) 测试。

意图锚点 (为什么这些行为重要):
- 专家规则 = 确定性零 LLM: matcher 行为必须逐个锁死, 否则静默放行/误杀。
- 语义规则 fail-open 可见: LLM 挂了不能拒掉资讯 (可用性 > 完备性),
  但必须留 semantic_rules_unavailable flag 让用户知道这层没生效。
- 预算封顶: 单批次 LLM 次数超限必须可见 (budget_exhausted), 防烧钱。
- gate 开关: 用户能整体关一层而不删规则; run_all 过滤必须生效。
- dry-run: 改规则前先看命中谁, 语义侧 LLM 只花 cap 次。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import register_routers
from backend.config import config
from backend.domain.models import HotspotItem
from backend.quality.base import GateContext
from backend.quality.config import QualityConfig
from backend.quality.custom_rules_gate import (
    ExpertFlagGate,
    ExpertRejectGate,
    SemanticRulesGate,
    clear_toggle_cache,
    gate_enabled,
)
from backend.quality.pipeline import QualityGatePipeline
from backend.repository import db
from backend.repository.hotspot_repo import HotspotRepository
from backend.repository.quality_custom_rules_repo import (
    QualityCustomRulesRepository,
)
from backend.repository.settings_repo import SettingsRepository


@pytest.fixture(autouse=True)
def _reset_toggle_cache():
    clear_toggle_cache()
    yield
    clear_toggle_cache()


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


def _item(
    *, id_: str = "q1", title: str = "OpenAI releases new GPT agent",
    summary: str = "summary text " * 5, source: str = "src_x",
    category: str = "ai", url: str = "https://example.com/q1",
) -> HotspotItem:
    now = datetime.now(timezone.utc)
    return HotspotItem(
        id=id_, title=title, summary=summary, source=source, url=url,
        category=category, published_at=now, fetched_at=now,
        ingested_at=now,
    )


def _ctx() -> GateContext:
    return GateContext(mode="loose")


# ---------------------------------------------------------------------------
# repo CRUD
# ---------------------------------------------------------------------------
def test_repo_crud_roundtrip_and_clamps(temp_db):
    repo = QualityCustomRulesRepository()
    r = repo.create(
        name="黑名单词", rule_kind="expert", match_kind="title_contains",
        match_value="免费领取", action="reject", deduction=999,
    )
    assert r["id"] >= 1 and r["deduction"] == 100  # 夹取 0-100
    r2 = repo.create(
        name="NL 规则", rule_kind="semantic", match_kind="nl",
        match_value="标题党式夸张表述",
    )
    assert r2["action"] == "flag"
    # update 白名单: rule_kind 不在 allowed, 不可被改
    repo.update(r["id"], {"deduction": 5, "rule_kind": "semantic"})
    assert repo.get(r["id"])["deduction"] == 5
    assert repo.get(r["id"])["rule_kind"] == "expert"
    assert repo.delete(r["id"]) == 1
    assert repo.get(r["id"]) is None
    assert {x["rule_kind"] for x in repo.list_rules()} == {"semantic"}


# ---------------------------------------------------------------------------
# 专家 matcher (确定性, 逐个锁行为)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("kind", "value", "hit"),
    [
        ("title_contains", "gpt AGENT", True),   # 大小写不敏感
        ("title_contains", "不存在", False),
        ("source_in", "A, B ,src_x", True),      # csv + 空格容错
        ("source_in", "other", False),
        ("category_equals", "ai", True),
        ("category_equals", "AI", False),        # 分类精确匹配
        ("url_matches", r"example\.com", True),
        ("url_matches", "([", False),            # 非法正则 → 不命中不崩
        ("summary_len_lt", "999", True),
        ("summary_len_lt", "abc", False),        # 非数字 → 不命中不崩
    ],
)
def test_match_expert_table(kind, value, hit):
    rule = {"id": 1, "match_kind": kind, "match_value": value}
    from backend.quality.custom_rules_gate import _match_expert
    assert _match_expert(rule, _item()) is hit


def test_scope_category_filters(temp_db):
    QualityCustomRulesRepository().create(
        name="仅安全域", rule_kind="expert", match_kind="title_contains",
        match_value="openai", action="flag", scope_category="security",
    )
    hit = ExpertFlagGate().check(_item(), _ctx())
    assert hit.passed  # scope 不匹配 → 不命中


# ---------------------------------------------------------------------------
# 三个 gate 行为
# ---------------------------------------------------------------------------
def test_expert_reject_gate_hard(temp_db):
    repo = QualityCustomRulesRepository()
    repo.create(name="拒", rule_kind="expert", match_kind="title_contains",
                match_value="openai", action="reject", deduction=50)
    res = ExpertRejectGate().check(_item(), _ctx())
    assert not res.passed and res.gate_name == "expert_reject"
    assert res.flags == [f"custom_rule_{1}"] and res.score_deduction == 50
    res2 = ExpertRejectGate().check(
        _item(id_="q2", title="别的标题"), _ctx())
    assert res2.passed


def test_expert_flag_gate_aggregates_hits(temp_db):
    repo = QualityCustomRulesRepository()
    repo.create(name="F1", rule_kind="expert", match_kind="title_contains",
                match_value="openai", action="flag", deduction=10)
    repo.create(name="F2", rule_kind="expert", match_kind="source_in",
                match_value="src_x", action="flag", deduction=25)
    res = ExpertFlagGate().check(_item(), _ctx())
    assert not res.passed
    assert res.score_deduction == 35  # 命中多条聚合扣分
    assert set(res.flags) == {"custom_rule_1", "custom_rule_2"}


def _patch_llm(monkeypatch, response):
    from backend.services.ai_hub import ai_service
    calls: list = []

    async def fake(messages, **kwargs):
        calls.append(messages)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(ai_service, "generate_text", fake)
    return calls


def test_semantic_gate_no_rules_never_calls_llm(temp_db, monkeypatch):
    calls = _patch_llm(monkeypatch, '{"violated": []}')
    ctx = _ctx()
    assert SemanticRulesGate().check(_item(), ctx).passed
    assert not calls  # 无规则 = 零 LLM (成本红线)


def test_semantic_gate_disabled_by_settings(temp_db, monkeypatch):
    QualityCustomRulesRepository().create(
        name="s", rule_kind="semantic", match_kind="nl", match_value="x")
    SettingsRepository().set("quality.semantic_rules.enabled", False)
    calls = _patch_llm(monkeypatch, '{"violated": []}')
    assert SemanticRulesGate().check(_item(), _ctx()).passed
    assert not calls


def test_semantic_gate_violation_deducts_per_rule(temp_db, monkeypatch):
    repo = QualityCustomRulesRepository()
    repo.create(name="s1", rule_kind="semantic", match_kind="nl",
                match_value="规则一", deduction=20)
    repo.create(name="s2", rule_kind="semantic", match_kind="nl",
                match_value="规则二", deduction=15)
    _patch_llm(monkeypatch, '{"violated": [2]}')  # 只违反第 2 条
    res = SemanticRulesGate().check(_item(), _ctx())
    assert not res.passed and res.score_deduction == 15
    assert res.flags == ["semantic_rule_2"]


def test_semantic_gate_fail_open_visible(temp_db, monkeypatch):
    """LLM 挂 → 零扣分放行但必须留可见 flag (fail-open 语义)。"""
    QualityCustomRulesRepository().create(
        name="s", rule_kind="semantic", match_kind="nl", match_value="x")
    _patch_llm(monkeypatch, RuntimeError("provider down"))
    res = SemanticRulesGate().check(_item(), _ctx())
    assert res.passed and res.score_deduction == 0
    assert res.flags == ["semantic_rules_unavailable"]


def test_semantic_gate_budget_cap_visible(temp_db, monkeypatch):
    """预算 1: 第 1 条正常判别, 第 2 条超限 → budget flag 可见零扣分。"""
    QualityCustomRulesRepository().create(
        name="s", rule_kind="semantic", match_kind="nl", match_value="x")
    SettingsRepository().set("quality.semantic_rules.max_per_batch", 1)
    _patch_llm(monkeypatch, '{"violated": []}')
    ctx = _ctx()
    assert SemanticRulesGate().check(_item(id_="a"), ctx).passed
    res2 = SemanticRulesGate().check(_item(id_="b"), ctx)
    assert res2.passed and res2.flags == ["semantic_rules_budget_exhausted"]


# ---------------------------------------------------------------------------
# gate 开关 + pipeline 过滤
# ---------------------------------------------------------------------------
def test_gate_enabled_default_and_toggle(temp_db):
    assert gate_enabled("expert_reject") is True  # 缺省开
    SettingsRepository().set("quality.gate.expert_flag.enabled", False)
    clear_toggle_cache()  # TTL 5s, 测试显式失效
    assert gate_enabled("expert_flag") is False


def test_run_all_skips_disabled_gate(temp_db):
    """关掉 expert_reject 后, 命中规则也不该再出 flag (过滤在 run_all 入口)。"""
    QualityCustomRulesRepository().create(
        name="拒", rule_kind="expert", match_kind="title_contains",
        match_value="openai", action="reject", deduction=50)
    cfg = QualityConfig()
    cfg._cache["strict_mode"] = False
    cfg._cache["min_score"] = 30
    pipe = QualityGatePipeline(cfg, log_repo=_NoopLogRepo())

    res = pipe.run_all(_item(), _ctx())
    assert "custom_rule_1" in res.final_flags  # 开 → 命中可见

    SettingsRepository().set("quality.gate.expert_reject.enabled", False)
    clear_toggle_cache()
    res2 = pipe.run_all(_item(), _ctx())
    assert not any(f.startswith("custom_rule_") for f in res2.final_flags)


class _NoopLogRepo:
    def write_log(self, item_id, result, mode="loose", checked_at=None):
        pass


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------
@pytest.fixture
def client(temp_db):
    app = FastAPI()
    register_routers(app)
    with TestClient(app) as c:
        yield c


def test_api_crud_validation_and_404(client):
    # expert 非法 match_kind → 422
    r = client.post("/api/quality/custom-rules", json={
        "name": "x", "rule_kind": "expert", "match_kind": "nl",
        "match_value": "v"})
    assert r.status_code == 422
    # semantic 强制 match_kind=nl + action=flag (语义层只软扣分)
    r = client.post("/api/quality/custom-rules", json={
        "name": "语义", "rule_kind": "semantic", "match_kind": "whatever",
        "match_value": "标题党", "action": "reject"})
    assert r.status_code == 200
    body = r.json()
    assert body["match_kind"] == "nl" and body["action"] == "flag"
    rid = body["id"]
    # list + kind 过滤
    assert len(client.get("/api/quality/custom-rules").json()["rules"]) == 1
    q = client.get("/api/quality/custom-rules?kind=expert").json()["rules"]
    assert q == []
    # update / 404 / delete / 404
    assert not client.put(f"/api/quality/custom-rules/{rid}",
                          json={"enabled": False}).json()["enabled"]
    assert client.put("/api/quality/custom-rules/999",
                      json={"enabled": True}).status_code == 404
    assert client.delete(f"/api/quality/custom-rules/{rid}").status_code == 200
    assert client.delete("/api/quality/custom-rules/999").status_code == 404


def test_api_gates_lists_14(client):
    gates = client.get("/api/quality/custom-rules/gates").json()["gates"]
    assert len(gates) == 14
    assert {g["name"] for g in gates} >= {
        "expert_reject", "expert_flag", "semantic_rules"}


def test_api_dry_run_expert_and_semantic(client, monkeypatch):
    HotspotRepository().upsert_many([
        _item(id_="d1"),  # 命中 openai flag 规则
        _item(id_="d2", title="无关条目", url="https://example.com/d2"),
    ])
    QualityCustomRulesRepository().create(
        name="F", rule_kind="expert", match_kind="title_contains",
        match_value="openai", action="flag", deduction=10)
    # 专家侧确定性: 只命中 d1, 零 LLM
    r = client.post("/api/quality/custom-rules/dry-run",
                    json={"limit": 20, "with_semantic": False})
    body = r.json()
    assert [h["item_id"] for h in body["expert"]["flag_hits"]] == ["d1"]
    assert body["semantic"]["ran"] == 0

    # 语义侧: with_semantic=True 才调 LLM; mock 按内容区分 — 只有
    # d2 ("无关条目") 判违反规则 1, d1 不违反 → hits 精确等于 [d2]
    QualityCustomRulesRepository().create(
        name="S", rule_kind="semantic", match_kind="nl",
        match_value="无聊条目", deduction=30)

    from backend.services.ai_hub import ai_service

    async def fake(messages, **kwargs):
        text = messages[-1]["content"]
        verdict = "[1]" if "无关条目" in text else "[]"
        return f'{{"violated": {verdict}}}'

    monkeypatch.setattr(ai_service, "generate_text", fake)
    r2 = client.post("/api/quality/custom-rules/dry-run",
                     json={"limit": 20, "with_semantic": True}).json()
    assert [h["item_id"] for h in r2["semantic"]["hits"]] == ["d2"]
    assert r2["semantic"]["ran"] == 2
