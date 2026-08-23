"""AIQualityGate 测试 (v4.4).

覆盖启发式 AI 生成/低信息密度检测:
- 营销词标题 → title_spam_words + 扣分
- 空标题 → empty_title
- 空摘要 → empty_summary
- 低努力信号 → heuristic_aigc_low_effort
- 正常高信息密度 → 通过
- LLM 检测委托 AIService (v4.4 集中式 AI 层); 无凭据时默认不触发
"""
import pytest

from backend.domain.models import HotspotItem
from backend.quality.ai_quality_gate import AIQualityGate
from backend.quality.base import GateContext


def _item(**over) -> HotspotItem:
    base = dict(
        id="t1", title="OpenAI 发布新的推理模型研究进展",
        summary="研究团队在多模态推理与可证明性方面取得阶段性成果，并计划开源权重与评测基准。",
        source="test", url="https://example.com/1", category="ai",
        published_at="2026-08-20T00:00:00Z", fetched_at="2026-08-20T00:00:00Z",
        is_fallback=False,
    )
    base.update(over)
    return HotspotItem(**base)


@pytest.fixture
def gate():
    return AIQualityGate()


@pytest.fixture
def ctx():
    return GateContext()


def test_normal_passes(gate, ctx):
    item = _item()
    r = gate.check(item, ctx)
    assert r.passed is True
    assert r.score_deduction == 0
    assert r.flags == []


def test_spam_title_flagged(gate, ctx):
    item = _item(title="震惊！AI 竟然可以这样，速看")
    r = gate.check(item, ctx)
    assert r.passed is False
    assert "title_spam_words" in r.flags
    assert r.score_deduction == gate.SPAM_TITLE_DED


def test_empty_title_flagged(gate, ctx):
    # title 有 Pydantic min_length=1，用纯空格（.strip() 后即空）
    item = _item(title="   ")
    r = gate.check(item, ctx)
    assert r.passed is False
    assert "empty_title" in r.flags
    assert r.score_deduction >= gate.EMPTY_TITLE_DED


def test_empty_summary_flagged(gate, ctx):
    item = _item(summary="   ")
    r = gate.check(item, ctx)
    assert r.passed is False
    assert "empty_summary" in r.flags


def test_low_effort_flagged(gate, ctx):
    # 标题 1 字符(<4) 且 摘要 1 字符(<20) → 低努力 (AI 敷衍生成形态)
    item = _item(title="A", summary="短")
    r = gate.check(item, ctx)
    assert "heuristic_aigc_low_effort" in r.flags


def test_llm_disabled_when_no_key(gate, ctx, monkeypatch):
    """无 LLM key 且 ollama 不可达时，ai_service.available()=False（不触发）。

    v4.4 重构后 LLM 检测委托 ai_service；monkeypatch 其凭据解析与
    ollama 探测，隔离外部网络/本机 ollama 时序影响。
    """
    import os

    from backend.services import ai_hub as ai_mod

    for k in ("SENSENOVA_API_KEY", "OPENAI_API_KEY", "QWEN_API_KEY",
              "ANTHROPIC_API_KEY"):
        os.environ.pop(k, None)
    monkeypatch.setattr(ai_mod.AIService, "_resolve_api_key", staticmethod(lambda: ""))
    monkeypatch.setattr(ai_mod.AIService, "_ollama_up", staticmethod(lambda *a, **k: False))
    assert gate._llm_detect("标题", "摘要", ctx) is None
    item = _item()
    r = gate.check(item, ctx)
    # 无 llm_ai_generated flag
    assert "llm_ai_generated" not in r.flags


def test_gate_detect_parses_content(monkeypatch):
    """ai_service.gate_detect 解析 OpenAI 兼容 choices[0].message.content。"""
    from backend.services.ai_hub import AIService

    svc = AIService()

    class _FakeResp:
        def __init__(self, payload): self._payload = payload
        def raise_for_status(self): pass
        def json(self): return self._payload

    captured = {}

    def _fake_post(self, url, json=None, headers=None):
        captured["url"] = url
        captured["headers"] = headers or {}
        captured["model"] = json["model"]
        captured["has_system"] = any(
            m["role"] == "system" for m in json["messages"]
        )
        return _FakeResp({"choices": [{"message": {"content": "0.9"}}]})

    monkeypatch.setattr("httpx.Client.post", _fake_post)

    score = svc._call_sensenova_detect("标题", "摘要", "fake-key", timeout=1.0)
    assert abs(score - 0.9) < 1e-6
    assert captured["url"].startswith("https://token.sensenova.cn")
    assert captured["model"] == "sensenova-6.8-flash-lite"
    assert captured["has_system"] is True


def test_gate_detect_network_fail_degrades(monkeypatch):
    """gate_detect 网络失败时返回 None（fail-open，不扣分降级）。"""
    from backend.services.ai_hub import AIService

    svc = AIService()
    monkeypatch.setattr(AIService, "_resolve_api_key", staticmethod(lambda: "fake-key"))
    monkeypatch.setattr(AIService, "_resolve_provider", staticmethod(lambda: "sensenova"))
    monkeypatch.setattr(
        "httpx.Client.post",
        lambda *a, **k: (_ for _ in ()).throw(ConnectionError("no network")),
    )
    r = svc.gate_detect("标题", "摘要")
    assert r is None


def test_llm_off_by_default_in_context(ctx):
    """默认 GateContext.llm_enabled=False → check 不走 LLM。"""
    from backend.quality.ai_quality_gate import AIQualityGate
    g = AIQualityGate()
    assert ctx.llm_enabled is False
    item = _item()
    r = g.check(item, ctx)
    assert "llm_ai_generated" not in r.flags


def test_llm_context_on_triggers(monkeypatch):
    """llm_enabled=True → check 调用 LLM 检测并扣分。"""
    from backend.domain.models import HotspotItem
    from backend.quality.ai_quality_gate import AIQualityGate
    from backend.quality.base import GateContext
    from backend.services import ai_hub as ai_mod

    # mock ai_service.gate_detect 返回高概率 (gate._llm_detect 委托它)
    monkeypatch.setattr(ai_mod.AIService, "available", lambda self, p=None: True)
    monkeypatch.setattr(ai_mod.AIService, "gate_detect", lambda *a, **k: 0.95)
    ctx = GateContext(llm_enabled=True)
    item = HotspotItem(
        id="t", title="普通标题", summary="有实质内容的摘要，包含具体信息与结论。",
        source="s", url="https://e.com/1", category="ai",
        published_at="2026-08-20T00:00:00Z", fetched_at="2026-08-20T00:00:00Z",
        is_fallback=False,
    )
    r = AIQualityGate().check(item, ctx)
    assert "llm_ai_generated" in r.flags
    assert r.score_deduction >= 30