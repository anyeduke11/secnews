"""density T3 (2026-09-24) — 关注域 AI 推荐 advisor 单元测试。

覆盖:
- build_recommendation_input: 确定性组装 (近 7d 域分布 + 30d 行为聚合 + 当前勾选),
  不含原始 URL/标题 (输入是统计不是精确值)
- get_recommendations: 域枚举校验 (越界丢弃) / fence JSON / 缓存 24h TTL /
  force 刷新 / 解析失败与 LLM 异常兜底 (返缓存或空, 不抛错)
- API: GET /api/interest/domains/recommendations 形状 / force 参数 /
  gate interest_engine 关闭时 404
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.services.interest_domain_advisor as advisor_mod
from backend.api import register_routers
from backend.api.middleware import TraceIDMiddleware
from backend.config import config
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.exceptions import register_exception_handlers
from backend.repository import db
from backend.repository.hotspot_repo import HotspotRepository, interest_insert_signal
from backend.repository.settings_repo import SettingsRepository
from backend.services.interest_engine_service import InterestEngineService


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_advisor.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture(autouse=True)
def _reset_engine_cache():
    InterestEngineService.invalidate_cache()
    yield
    InterestEngineService.invalidate_cache()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed_hotspots(n_ai: int = 3, n_vuln: int = 1) -> None:
    now = datetime.now(timezone.utc)
    items = [
        HotspotItem(
            id=f"h-ai-{i}",
            title=f"大模型提示注入攻防研究 {i}",
            source="test",
            url=f"https://example.com/ai-{i}",
            category=Category.AI,
            published_at=now - timedelta(hours=1),
            fetched_at=now,
            ingested_at=now,
            quality_flags=[],
        )
        for i in range(n_ai)
    ] + [
        HotspotItem(
            id="h-vuln-1",
            title="某 CMS 远程代码执行漏洞 CVE-2026-1234 分析",
            source="test",
            url="https://example.com/vuln-1",
            category=Category.SECURITY,
            published_at=now - timedelta(hours=2),
            fetched_at=now,
            ingested_at=now,
            quality_flags=[],
        )
        for _ in range(n_vuln)
    ]
    HotspotRepository().upsert_many(items)


def _seed_signal(domain: str = "ai_security", weight: float = 2.0) -> None:
    interest_insert_signal("h-ai-0", domain, "deep_read", weight, _now_iso())


class _FakeGenerate:
    """llm_service.generate 替身: 队列式返回, 记录调用次数与 prompt。"""

    def __init__(self, replies: list[str | Exception]):
        self.replies = list(replies)
        self.calls: list[dict] = []

    async def __call__(self, prompt: str, *, task: str, **kwargs):
        self.calls.append({"prompt": prompt, "task": task, **kwargs})
        if not self.replies:
            raise AssertionError("unexpected llm call")
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _install_llm(monkeypatch: pytest.MonkeyPatch, replies: list[str | Exception]) -> _FakeGenerate:
    fake = _FakeGenerate(replies)

    class _FakeLLM:
        generate = fake

    class _FakeAiHub:
        llm_service = _FakeLLM()

    monkeypatch.setattr(advisor_mod, "_ai_hub_mod", _FakeAiHub)
    return fake


VALID_REPLY = json.dumps({
    "recommended": ["ai_security", "vuln_research", "not_a_domain", "pentest"],
    "reasons": {
        "ai_security": "近期 AI 安全内容占比与行为分均高",
        "vuln_research": "近 7 天漏洞类入库持续出现",
        "not_a_domain": "越界理由应被丢弃",
        "pentest": "行为信号显示渗透方向兴趣",
    },
}, ensure_ascii=False)


# ── build_recommendation_input ────────────────────────────────


class TestBuildInput:
    def test_input_aggregates_three_channels(self, temp_db):
        _seed_hotspots()
        _seed_signal("ai_security")
        SettingsRepository().set("interest.practice_domains", ["compliance"])

        data = advisor_mod.build_recommendation_input()

        assert data["current_selected"] == ["compliance"]
        dist = {d["domain"]: d for d in data["ingest_7d"]}
        assert dist["ai_security"]["count"] == 3
        assert dist["vuln_research"]["count"] == 1
        assert dist["ai_security"]["share"] > dist["vuln_research"]["share"]
        beh = {d["domain"]: d for d in data["behavior_30d"]}
        assert beh["ai_security"]["events_30d"] == 1

    def test_input_has_no_raw_url_or_title(self, temp_db):
        _seed_hotspots()
        _seed_signal("ai_security")
        blob = json.dumps(advisor_mod.build_recommendation_input(), ensure_ascii=False)
        assert "https://" not in blob
        assert "提示注入" not in blob  # 统计口径: 原始标题不得进入 prompt


# ── get_recommendations ────────────────────────────────────────


class TestGetRecommendations:
    def test_valid_reply_filtered_and_cached(self, temp_db, monkeypatch):
        _install_llm(monkeypatch, [VALID_REPLY])
        result = asyncio.run(advisor_mod.get_recommendations())
        # 越界域丢弃 + 截断 ≤5
        assert result["recommended"] == ["ai_security", "vuln_research", "pentest"]
        assert set(result["reasons"]) == {"ai_security", "vuln_research", "pentest"}
        assert result["note"] == ""
        assert result["cached_at"]
        # 缓存已落 kv
        cached = SettingsRepository().get("interest.advisor_cache")
        assert cached["recommended"] == result["recommended"]

    def test_fenced_json_parsed(self, temp_db, monkeypatch):
        _install_llm(monkeypatch, ["```json\n" + VALID_REPLY + "\n```"])
        result = asyncio.run(advisor_mod.get_recommendations())
        assert result["recommended"] == ["ai_security", "vuln_research", "pentest"]

    def test_truncate_to_five(self, temp_db, monkeypatch):
        seven = [
            "network_security", "pentest", "vuln_research", "incident_response",
            "appsec", "crypto_security", "data_security",
        ]
        reply = json.dumps({
            "recommended": seven,
            "reasons": dict.fromkeys(seven, "r"),
        })
        _install_llm(monkeypatch, [reply])
        result = asyncio.run(advisor_mod.get_recommendations())
        assert len(result["recommended"]) == 5

    def test_cache_hit_skips_llm(self, temp_db, monkeypatch):
        fake = _install_llm(monkeypatch, [VALID_REPLY])
        first = asyncio.run(advisor_mod.get_recommendations())
        second = asyncio.run(advisor_mod.get_recommendations())
        assert len(fake.calls) == 1
        assert second["cached_at"] == first["cached_at"]

    def test_force_refreshes(self, temp_db, monkeypatch):
        fake = _install_llm(monkeypatch, [VALID_REPLY, VALID_REPLY])
        asyncio.run(advisor_mod.get_recommendations())
        asyncio.run(advisor_mod.get_recommendations(force=True))
        assert len(fake.calls) == 2

    def test_expired_cache_refreshes(self, temp_db, monkeypatch):
        fake = _install_llm(monkeypatch, [VALID_REPLY])
        asyncio.run(advisor_mod.get_recommendations())
        stale = datetime.now(timezone.utc) - timedelta(hours=25)
        cached = SettingsRepository().get("interest.advisor_cache")
        cached["cached_at"] = stale.isoformat()
        SettingsRepository().set("interest.advisor_cache", cached)
        fake.replies.append(VALID_REPLY)

        asyncio.run(advisor_mod.get_recommendations())
        assert len(fake.calls) == 2

    def test_parse_failure_returns_last_cache(self, temp_db, monkeypatch):
        _install_llm(monkeypatch, [VALID_REPLY, "not json at all"])
        good = asyncio.run(advisor_mod.get_recommendations())
        bad = asyncio.run(advisor_mod.get_recommendations(force=True))
        assert bad["recommended"] == good["recommended"]
        assert bad["cached_at"] == good["cached_at"]
        assert bad["note"]

    def test_parse_failure_no_cache_returns_empty(self, temp_db, monkeypatch):
        _install_llm(monkeypatch, ["garbage"])
        result = asyncio.run(advisor_mod.get_recommendations())
        assert result["recommended"] == []
        assert result["reasons"] == {}
        assert result["note"]

    def test_llm_exception_returns_empty_no_raise(self, temp_db, monkeypatch):
        _install_llm(monkeypatch, [RuntimeError("all providers down")])
        result = asyncio.run(advisor_mod.get_recommendations())
        assert result["recommended"] == []
        assert result["note"]


# ── prompt ─────────────────────────────────────────────────────


class TestPrompt:
    def test_prompt_embeds_domain_enum_and_contract(self):
        from backend.services.ai_hub.prompts import build_interest_advisor_prompt
        from backend.services.auto_classifier import PRACTICE_DOMAIN_LABELS

        prompt = build_interest_advisor_prompt(
            ingest_7d=[{"domain": "ai_security", "count": 3, "share": 0.75}],
            behavior_30d=[{"domain": "ai_security", "score": 1.0, "events_30d": 2}],
            current_selected=["compliance"],
            domain_labels=PRACTICE_DOMAIN_LABELS,
        )
        for domain in PRACTICE_DOMAIN_LABELS:
            assert domain in prompt
        assert "recommended" in prompt and "reasons" in prompt
        assert "ai_security" in prompt  # 输入统计进入 prompt


# ── API ────────────────────────────────────────────────────────


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(TraceIDMiddleware)
    register_exception_handlers(app)
    register_routers(app)
    return TestClient(app)


class TestAPI:
    def test_get_recommendations_endpoint(self, temp_db, monkeypatch):
        _install_llm(monkeypatch, [VALID_REPLY])
        resp = _client().get("/api/interest/domains/recommendations")
        assert resp.status_code == 200
        body = resp.json()
        assert body["recommended"] == ["ai_security", "vuln_research", "pentest"]
        assert body["cached_at"]
        assert "note" in body

    def test_force_query_param_triggers_refresh(self, temp_db, monkeypatch):
        fake = _install_llm(monkeypatch, [VALID_REPLY, VALID_REPLY])
        client = _client()
        client.get("/api/interest/domains/recommendations")
        client.get("/api/interest/domains/recommendations?force=1")
        assert len(fake.calls) == 2

    def test_gate_disabled_404(self, monkeypatch):
        import backend.extensions as extensions

        extensions.reset_gates()
        monkeypatch.setattr(
            extensions, "_load_gates", lambda: {"interest_engine": False}
        )
        app = FastAPI()
        register_routers(app)
        with TestClient(app) as client:
            resp = client.get("/api/interest/domains/recommendations")
        assert resp.status_code == 404
        extensions.reset_gates()
