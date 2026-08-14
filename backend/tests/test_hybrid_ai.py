"""Tests for DegradationMatrix, CostMonitor, and T1/T3 hybrid AI integration.

Phase 16 — Hybrid AI 配置降级 + 成本监控 + T1/T3 LLM 集成测试。

Coverage
--------
1. DegradationMatrix (7 tests):
   - 5 种降级场景: no_config, disabled, no_provider, ollama_only, full
   - status() 方法返回正确 JSON
   - create_degradation_matrix() 工厂函数

2. CostMonitor (7 tests):
   - record_usage() 写入 DB
   - check_limits() 无超限 / 日限额超限 / 月限额超限
   - get_daily_cost() / get_monthly_cost()
   - get_on_exceeded_strategy()
   - _estimate_cost() 静态函数

3. T1/T3 Hybrid (3 tests):
   - T1 _score_with_llm() 调用 llm_service.score() 并正确回退
   - T3 _summarize_with_llm() 调用 llm_service.summarize() 并正确回退

共 17 个测试用例。
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.config import config as app_config
from backend.config.degradation_matrix import (
    DEGRADATION_SCENARIOS,
    DegradationMatrix,
    create_degradation_matrix,
)
from backend.config.llm_schema import (
    CostAlert,
    LLMConfig,
    ProviderConfig,
    ProviderModels,
)
from backend.metrics.kl_metrics import kl_metrics
from backend.repository import db as db_module
from backend.repository.db import get_connection
from backend.services.cost_monitor import CostMonitor, _estimate_cost
from backend.services.llm_service import llm_service
from backend.services.triggers import T1Trigger, T3Trigger

# ===================================================================
# Helpers
# ===================================================================

def _make_provider(
    ptype: str = "ollama",
    base_url: str | None = None,
    api_key_env: str | None = None,
) -> ProviderConfig:
    """Create a minimal ProviderConfig for testing."""
    return ProviderConfig(
        type=ptype,  # type: ignore[arg-type]
        base_url=base_url,
        api_key_env=api_key_env,
        models=ProviderModels(),
    )


def _make_llm_config(
    enabled: bool = True,
    providers: dict[str, ProviderConfig] | None = None,
    fallback_order: list[str] | None = None,
    daily_usd_limit: float = 5.0,
    monthly_usd_limit: float = 100.0,
    on_exceeded: str = "warn",
) -> LLMConfig:
    """Create a minimal LLMConfig for testing (skip validation via model_construct)."""
    if providers is None:
        providers = {
            "ollama": _make_provider("ollama", base_url="http://127.0.0.1:11434"),
            "openai": _make_provider("openai", api_key_env="OPENAI_API_KEY"),
        }
    if fallback_order is None:
        fallback_order = ["ollama", "openai"]
    default_provider = fallback_order[0] if fallback_order else ""
    return LLMConfig.model_construct(
        enabled=enabled,
        default_provider=default_provider,
        fallback_order=fallback_order,
        providers=providers,
        cost_alert=CostAlert(
            daily_usd_limit=daily_usd_limit,
            monthly_usd_limit=monthly_usd_limit,
            on_exceeded=on_exceeded,  # type: ignore[arg-type]
        ),
    )


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Create an isolated test DB with all migrations applied."""
    test_db = tmp_path / "test_hybrid_ai.db"
    monkeypatch.setattr(app_config, "db_path", test_db)
    db_module.close_db()
    db_module.init_db()
    yield test_db
    db_module.close_db()


@pytest.fixture
def fresh_metrics():
    """Reset the shared metrics singleton between tests."""
    kl_metrics.reset_counters()
    kl_metrics.reset_histograms()
    kl_metrics.set_stage_counts({})
    yield kl_metrics
    kl_metrics.reset_counters()
    kl_metrics.reset_histograms()
    kl_metrics.set_stage_counts({})


# ===================================================================
# DegradationMatrix — 5 种降级场景
# ===================================================================

class TestDegradationMatrix:
    """DegradationMatrix: 5 种场景 + status() + 工厂函数."""

    def test_matrix_no_config(self):
        """config=None → scenario='no_config'."""
        matrix = DegradationMatrix(config=None)
        assert matrix.scenario == "no_config"
        assert matrix.description == DEGRADATION_SCENARIOS["no_config"]
        assert matrix.requires_external_agent is True
        assert matrix.t1_available is True
        assert matrix.t3_available is True

    def test_matrix_disabled(self):
        """enabled=False → scenario='disabled'."""
        cfg = _make_llm_config(enabled=False)
        matrix = DegradationMatrix(cfg)
        assert matrix.scenario == "disabled"
        assert matrix.description == DEGRADATION_SCENARIOS["disabled"]
        assert matrix.requires_external_agent is True
        assert matrix.t1_available is True
        assert matrix.t3_available is True

    def test_matrix_no_provider(self):
        """空 providers → scenario='no_provider'."""
        cfg = _make_llm_config(providers={}, fallback_order=[])
        matrix = DegradationMatrix(cfg)
        assert matrix.scenario == "no_provider"
        assert matrix.description == DEGRADATION_SCENARIOS["no_provider"]
        assert matrix.requires_external_agent is False
        assert matrix.t1_available is False
        assert matrix.t3_available is False

    def test_matrix_ollama_only(self):
        """仅 Ollama → scenario='ollama_only'."""
        providers = {
            "ollama": _make_provider("ollama", base_url="http://127.0.0.1:11434"),
        }
        cfg = _make_llm_config(providers=providers, fallback_order=["ollama"])
        matrix = DegradationMatrix(cfg)
        assert matrix.scenario == "ollama_only"
        assert matrix.description == DEGRADATION_SCENARIOS["ollama_only"]
        assert matrix.requires_external_agent is False
        assert matrix.t1_available is True
        assert matrix.t3_available is True

    def test_matrix_full(self):
        """Ollama + API provider → scenario='full'."""
        providers = {
            "ollama": _make_provider("ollama", base_url="http://127.0.0.1:11434"),
            "openai": _make_provider("openai", api_key_env="OPENAI_API_KEY"),
        }
        cfg = _make_llm_config(providers=providers, fallback_order=["ollama", "openai"])
        matrix = DegradationMatrix(cfg)
        assert matrix.scenario == "full"
        assert matrix.description == DEGRADATION_SCENARIOS["full"]
        assert matrix.requires_external_agent is False
        assert matrix.t1_available is True
        assert matrix.t3_available is True

    def test_matrix_status(self):
        """status() 返回正确 JSON 结构."""
        providers = {
            "ollama": _make_provider("ollama", base_url="http://127.0.0.1:11434"),
        }
        cfg = _make_llm_config(providers=providers, fallback_order=["ollama"])
        matrix = DegradationMatrix(cfg)
        status = matrix.status()
        assert status["scenario"] == "ollama_only"
        assert status["description"] == DEGRADATION_SCENARIOS["ollama_only"]
        assert status["requires_external_agent"] is False
        assert status["t1_available"] is True
        assert status["t3_available"] is True
        assert status["llm_enabled"] is True
        assert status["default_provider"] == "ollama"
        assert status["fallback_order"] == ["ollama"]

    def test_matrix_status_no_config(self):
        """config=None 时 status() 返回 llm_enabled=False."""
        matrix = DegradationMatrix(config=None)
        status = matrix.status()
        assert status["scenario"] == "no_config"
        assert status["llm_enabled"] is False
        assert status["default_provider"] is None
        assert status["fallback_order"] == []

    def test_create_degradation_matrix_no_file(self, tmp_path, monkeypatch):
        """create_degradation_matrix() 当文件不存在时返回 no_config 矩阵."""
        fake_path = tmp_path / "nonexistent.yaml"
        monkeypatch.setattr(
            "backend.config.degradation_matrix.load_llm_config",
            lambda _path=None: None,
        )
        matrix = create_degradation_matrix(fake_path)
        assert matrix.scenario == "no_config"


# ===================================================================
# CostMonitor
# ===================================================================

class TestCostMonitor:
    """CostMonitor: record_usage, check_limits, cost queries, estimate."""

    def test_estimate_cost(self):
        """_estimate_cost 对已知/未知模型和零 token 返回正确值."""
        # 已知模型
        assert _estimate_cost("gpt-4o-mini", 1_000_000) == 0.15
        assert _estimate_cost("gpt-4o", 1_000_000) == 5.0
        # 未知模型 → 默认 $0.5/1M
        assert _estimate_cost("unknown-model", 1_000_000) == 0.5
        # 零 token
        assert _estimate_cost("gpt-4o-mini", 0) == 0.0
        # 负 token
        assert _estimate_cost("gpt-4o-mini", -100) == 0.0

    def test_record_usage(self, temp_db):
        """record_usage() 写入 DB 后可读出."""
        monitor = CostMonitor()
        monitor.record_usage(
            provider="openai",
            model="gpt-4o-mini",
            task="score",
            tokens=150,
            cost_usd=0.0001,
            latency_ms=250,
        )
        conn = get_connection()
        rows = conn.execute(
            "SELECT provider, model, task, tokens, cost_usd, latency_ms "
            "FROM llm_usage_log"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["provider"] == "openai"
        assert rows[0]["model"] == "gpt-4o-mini"
        assert rows[0]["task"] == "score"
        assert rows[0]["tokens"] == 150
        assert rows[0]["cost_usd"] == 0.0001
        assert rows[0]["latency_ms"] == 250

    def test_record_usage_multiple(self, temp_db):
        """多次 record_usage() 累积写入."""
        monitor = CostMonitor()
        for _i in range(3):
            monitor.record_usage("ollama", "qwen2.5:7b", "score", 100, 0.0, 50)
        conn = get_connection()
        rows = conn.execute(
            "SELECT COUNT(*) AS cnt FROM llm_usage_log"
        ).fetchone()
        assert rows["cnt"] == 3

    def test_get_daily_cost_empty(self, temp_db):
        """无记录时 get_daily_cost() 返回 0.0."""
        monitor = CostMonitor()
        assert monitor.get_daily_cost() == 0.0

    def test_get_monthly_cost_empty(self, temp_db):
        """无记录时 get_monthly_cost() 返回 0.0."""
        monitor = CostMonitor()
        assert monitor.get_monthly_cost() == 0.0

    def test_get_daily_cost_with_data(self, temp_db):
        """有记录时 get_daily_cost() 返回正确总和."""
        monitor = CostMonitor()
        monitor.record_usage("openai", "gpt-4o-mini", "score", 100, 0.5, 100)
        monitor.record_usage("openai", "gpt-4o-mini", "score", 100, 1.5, 100)
        assert monitor.get_daily_cost() == 2.0

    def test_check_limits_no_limit(self, temp_db):
        """未超限额时 check_limits() 返回 True."""
        monitor = CostMonitor()
        # 无配置 → 不检查 → True
        assert monitor.check_limits() is True

    def test_check_limits_daily_exceeded(self, temp_db, monkeypatch):
        """日限额超限时 check_limits() 返回 False."""
        cfg = _make_llm_config(daily_usd_limit=1.0, monthly_usd_limit=100.0)
        monitor = CostMonitor(cfg)
        # 插入超限数据
        conn = get_connection()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO llm_usage_log (provider, model, task, tokens, cost_usd, latency_ms, occurred_at) "
            "VALUES ('openai', 'gpt-4o-mini', 'score', 100, 2.0, 0, ?)",
            (now,),
        )
        # Mock _trigger_alert 避免 cg_events 表列名不匹配
        monkeypatch.setattr(CostMonitor, "_trigger_alert", lambda *a, **kw: None)
        assert monitor.check_limits() is False

    def test_check_limits_monthly_exceeded(self, temp_db, monkeypatch):
        """月限额超限时 check_limits() 返回 False."""
        cfg = _make_llm_config(daily_usd_limit=100.0, monthly_usd_limit=5.0)
        monitor = CostMonitor(cfg)
        # 插入数据，日限额内但月限额超
        conn = get_connection()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO llm_usage_log (provider, model, task, tokens, cost_usd, latency_ms, occurred_at) "
            "VALUES ('openai', 'gpt-4o-mini', 'score', 100, 10.0, 0, ?)",
            (now,),
        )
        monkeypatch.setattr(CostMonitor, "_trigger_alert", lambda *a, **kw: None)
        assert monitor.check_limits() is False

    def test_get_on_exceeded_strategy_default(self):
        """无配置时 get_on_exceeded_strategy() 返回 'warn'."""
        monitor = CostMonitor()
        assert monitor.get_on_exceeded_strategy() == "warn"

    def test_get_on_exceeded_strategy_configured(self):
        """配置为 block 时返回 'block'."""
        cfg = _make_llm_config(on_exceeded="block")
        monitor = CostMonitor(cfg)
        assert monitor.get_on_exceeded_strategy() == "block"


# ===================================================================
# T1/T3 Hybrid AI 集成
# ===================================================================

class TestT1Hybrid:
    """T1 _score_with_llm 的 LLM 集成与回退."""

    def test_t1_score_with_llm_calls_service(self, temp_db, fresh_metrics, monkeypatch):
        """_score_with_llm() 调用 llm_service.score() 并返回 LLM 评分."""
        # ai_scores 有外键到 hotspots，需要先插入父记录
        conn = get_connection()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT OR IGNORE INTO hotspots (id, title, source, url, category, published_at, fetched_at) "
            "VALUES ('test-1', 'AI Security Paper', 'web', 'https://x.test/1', 'ai', ?, ?)",
            (now, now),
        )

        # 模拟 llm_service.score 返回高分
        async def fake_score(content: str, hotspot_id: str = "") -> float:
            return 8.5
        monkeypatch.setattr(llm_service, "score", fake_score)

        t1 = T1Trigger(metrics=fresh_metrics)
        item = {"id": "test-1", "title": "AI Security Paper", "concepts": '["llm", "red team"]', "tags": "[]"}
        score = t1._score_with_llm(item)
        assert score == 8.5

        # LLM 评分已写入 ai_scores 表
        row = conn.execute(
            "SELECT score, reason FROM ai_scores WHERE hotspot_id = ?", ("test-1",)
        ).fetchone()
        assert row is not None
        assert row["score"] == 8.5
        assert row["reason"] == "llm_service"

    def test_t1_score_with_llm_fallback_to_db(self, temp_db, fresh_metrics, monkeypatch):
        """LLM 失败时回退到 ai_scores 中的评分."""
        # ai_scores 有外键到 hotspots，需要先插入父记录
        conn = get_connection()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT OR IGNORE INTO hotspots (id, title, source, url, category, published_at, fetched_at) "
            "VALUES ('test-2', 'Some Article', 'web', 'https://x.test/2', 'ai', ?, ?)",
            (now, now),
        )
        # 预设数据库评分
        conn.execute(
            "INSERT INTO ai_scores (hotspot_id, score, reason, scored_at) "
            "VALUES ('test-2', 3.5, 'test', ?)",
            (now,),
        )

        # 模拟 llm_service.score 抛出异常
        async def fake_score_fail(content: str, hotspot_id: str = "") -> float:
            raise RuntimeError("LLM unavailable")
        monkeypatch.setattr(llm_service, "score", fake_score_fail)

        t1 = T1Trigger(metrics=fresh_metrics)
        item = {"id": "test-2", "title": "Some Article", "concepts": "[]", "tags": "[]"}
        score = t1._score_with_llm(item)
        # 回退到数据库评分 3.5
        assert score == 3.5

    def test_t1_score_with_llm_fallback_to_default(self, temp_db, fresh_metrics, monkeypatch):
        """LLM 失败且无数据库评分时回退到 DEFAULT_SCORE (5.0)."""
        async def fake_score_fail(content: str, hotspot_id: str = "") -> float:
            raise RuntimeError("LLM unavailable")
        monkeypatch.setattr(llm_service, "score", fake_score_fail)

        t1 = T1Trigger(metrics=fresh_metrics)
        item = {"id": "test-3", "title": "No DB Score", "concepts": "[]", "tags": "[]"}
        score = t1._score_with_llm(item)
        from backend.services.triggers.t1_raw_to_refine import DEFAULT_SCORE as T1_DEFAULT
        assert score == T1_DEFAULT


class TestT3Hybrid:
    """T3 _summarize_with_llm 的 LLM 集成与回退."""

    def test_t3_summarize_with_llm_calls_service(self, temp_db, fresh_metrics, monkeypatch):
        """_summarize_with_llm() 调用 llm_service.summarize() 并返回摘要."""
        async def fake_summarize(chunks: list[str]) -> str:
            return "This is an LLM-generated summary."
        monkeypatch.setattr(llm_service, "summarize", fake_summarize)

        t3 = T3Trigger(metrics=fresh_metrics)
        item = {"id": "t3-1", "title": "Article Title", "content": "Long article content here..."}
        summary = t3._summarize_with_llm(item)
        assert summary == "This is an LLM-generated summary."

    def test_t3_summarize_with_llm_fallback(self, temp_db, fresh_metrics, monkeypatch):
        """LLM 失败时回退到 _generate_summary (前 200 字符)."""
        async def fake_summarize_fail(chunks: list[str]) -> str:
            raise RuntimeError("LLM unavailable")
        monkeypatch.setattr(llm_service, "summarize", fake_summarize_fail)

        t3 = T3Trigger(metrics=fresh_metrics)
        content = "A" * 500
        item = {"id": "t3-2", "title": "Article Title", "content": content}
        summary = t3._summarize_with_llm(item)
        assert summary == content[:200]
        assert len(summary) == 200

    def test_t3_summarize_with_llm_empty_content(self, temp_db, fresh_metrics, monkeypatch):
        """空内容时 LLM 不被调用，直接回退到 _generate_summary."""
        call_count = 0

        async def fake_summarize(chunks: list[str]) -> str:
            nonlocal call_count
            call_count += 1
            return "should not be called"
        monkeypatch.setattr(llm_service, "summarize", fake_summarize)

        t3 = T3Trigger(metrics=fresh_metrics)
        item = {"id": "t3-3", "title": "", "content": ""}
        summary = t3._summarize_with_llm(item)
        assert summary == ""
        # LLM 未被调用（内容为空，跳过 LLM 调用）
        assert call_count == 0