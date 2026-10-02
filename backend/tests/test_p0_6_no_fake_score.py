"""v0.8.6 P0-6 (审计 E3): DEFAULT_SCORE 假成功删除 — AI 失败 = failed。

E3 缺陷 (修复前): score 解析失败回落 DEFAULT_SCORE=5.0 并缓存、记
ok=True — 模型拒绝/超时被记成"评分 5.0 成功" (1,006 次静默失败的构成)。

验收 (PRD P0-6): 构造超时/解析失败用例, 断言 failed 而非 5.0。
"""
from __future__ import annotations

import pytest

from backend.config.llm_schema import LLMConfig
from backend.repository.db import get_connection
from backend.services.ai_hub import LLMService, ScoreParseError
from backend.services.ai_hub.prompts import _make_cache_key

from .test_llm_service import _make_provider_config  # 复用 provider 构造


@pytest.fixture
def one_provider_config():
    return LLMConfig(
        enabled=True,
        default_provider="prov_a",
        fallback_order=["prov_a"],
        providers={
            "prov_a": _make_provider_config(
                ptype="openai", base_url="https://a.example/v1",
                api_key_env="X_A_KEY", models={"score": "m-a"},
            ),
        },
    )


def _svc(monkeypatch, cfg) -> LLMService:
    monkeypatch.setattr(
        "backend.services.ai_hub.gateway.load_llm_config", lambda _p=None: cfg
    )
    return LLMService()


# ---------------------------------------------------------------------------
# 验收 1: 全 provider 超时/失败 → score() 返回 None (不是 5.0)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeout_returns_none_not_fake_score(temp_db, one_provider_config, monkeypatch):
    """E3 验收: 超时 → None + llm_usage_log ok=0 (failed 而非 5.0 成功)。"""
    svc = _svc(monkeypatch, one_provider_config)

    async def _timeout(*a, **kw):
        raise TimeoutError("read timeout")

    monkeypatch.setattr(svc, "_call_provider", _timeout)
    result = await svc.score("article body")
    assert result is None, "全 provider 失败必须返回 None (E3: 不得假 5.0)"

    rows = get_connection().execute(
        "SELECT ok, error FROM llm_usage_log WHERE task='score' ORDER BY id DESC LIMIT 1"
    ).fetchall()
    assert rows and rows[0]["ok"] == 0
    assert "timeout" in rows[0]["error"].lower()


# ---------------------------------------------------------------------------
# 验收 2: 响应解析不出分数 → 该 provider 记 failed、不缓存、不假成功
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unparseable_response_failed_not_cached(
    temp_db, one_provider_config, monkeypatch
):
    """E3 核心: 模型返回无数字文本 (拒绝/截断) → ok=0 + 不写缓存 + 全链后 None。"""
    svc = _svc(monkeypatch, one_provider_config)

    async def _gibberish(*a, **kw):
        return "抱歉，我无法为这篇文章评分。"  # 无数字 → 解析必失败

    monkeypatch.setattr(svc, "_call_provider", _gibberish)
    result = await svc.score("article body")
    assert result is None

    # 记账: ok=0 + error 注明 unparseable (而非 ok=1 假成功)
    row = get_connection().execute(
        "SELECT ok, error FROM llm_usage_log WHERE task='score' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row["ok"] == 0
    assert "unparseable" in row["error"].lower()

    # 不缓存: 垃圾响应不得污染缓存 (修复前 5.0 会被缓存, 后续同内容直接假命中)
    from backend.services.ai_hub.cache import get_llm_cache
    assert get_llm_cache(_make_cache_key("score", "article body")) is None


@pytest.mark.asyncio
async def test_parse_success_still_works_and_caches(
    temp_db, one_provider_config, monkeypatch
):
    """回归: 正常数字响应照常返回/缓存/记 ok=1 (修复不伤正常路径)。"""
    svc = _svc(monkeypatch, one_provider_config)

    async def _ok(*a, **kw):
        return "8.5"

    monkeypatch.setattr(svc, "_call_provider", _ok)
    assert await svc.score("article body") == 8.5
    # 第二次命中缓存
    assert await svc.score("article body") == 8.5
    row = get_connection().execute(
        "SELECT ok FROM llm_usage_log WHERE task='score' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row["ok"] == 1


# ---------------------------------------------------------------------------
# _parse_score: 解析失败抛 ScoreParseError (常量级)
# ---------------------------------------------------------------------------


def test_parse_score_raises_on_no_number():
    with pytest.raises(ScoreParseError):
        LLMService._parse_score("no digits here")


def test_parse_score_empty():
    with pytest.raises(ScoreParseError):
        LLMService._parse_score("")


def test_default_score_constant_gone():
    """P0-6 验收: DEFAULT_SCORE 常量已从 ai_hub 公开 API 删除。"""
    import backend.services.ai_hub as hub

    assert not hasattr(hub, "DEFAULT_SCORE")


# ---------------------------------------------------------------------------
# evaluate 链: 模型没给 score 字段 → quality_score=None (不编造 5.0)
# ---------------------------------------------------------------------------


def test_parse_eval_json_missing_score_is_none():
    from backend.services.ai_hub import _parse_eval_json

    raw = '{"verdict": "还行", "summary": "s", "key_points": ["a"]}'
    out = _parse_eval_json(raw, provider="p")
    assert out["quality_score"] is None
    assert out["verdict"] == "还行"


def test_parse_eval_json_with_score_unchanged():
    from backend.services.ai_hub import _parse_eval_json

    out = _parse_eval_json('{"score": 7.2, "verdict": "v"}', provider="p")
    assert out["quality_score"] == 7.2
