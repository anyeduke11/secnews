"""AIQualityGate 测试 (v4.4).

覆盖启发式 AI 生成/低信息密度检测:
- 营销词标题 → title_spam_words + 扣分
- 空标题 → empty_title
- 空摘要 → empty_summary
- 低努力信号 → heuristic_aigc_low_effort
- 正常高信息密度 → 通过
- LLM 接口预留 → 默认不启用 (env 无 key 时 _llm_available=False)
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
    """无 LLM key 且 ollama 不可达时，_llm_available=False（接口不触发）。

    用 monkeypatch 把 _ollama_up 固定为 False，隔离外部网络/时序影响。
    """
    import os
    for k in ("SENSENOVA_API_KEY", "OPENAI_API_KEY", "QWEN_API_KEY",
              "ANTHROPIC_API_KEY"):
        os.environ.pop(k, None)
    # 隔离 ollama 探测（避免本地 ollama 运行时误判为可用）
    monkeypatch.setattr(
        "backend.quality.ai_quality_gate._ollama_up", lambda *a, **k: False
    )
    assert gate._llm_available() is False
    item = _item()
    r = gate.check(item, ctx)
    # 无 llm_ai_generated flag
    assert "llm_ai_generated" not in r.flags


def test_call_sensenova_parses_content(monkeypatch, gate):
    """_call_sensenova 解析 OpenAI 兼容 choices[0].message.content。"""
    import json

    class _FakeResp:
        def __init__(self, body): self._body = body
        def read(self): return self._body.encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    captured = {}

    def _fake_urlopen(req, timeout=8):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.headers)
        payload = json.loads(req.data.decode())
        captured["model"] = payload["model"]
        captured["has_system"] = any(
            m["role"] == "system" for m in payload["messages"]
        )
        body = {"choices": [{"message": {"content": "0.9"}}]}
        return _FakeResp(json.dumps(body))

    # monkeypatch 模块级 urllib.request.urlopen（_call_sensenova 用模块级引用）
    monkeypatch.setattr("backend.quality.ai_quality_gate.urllib.request.urlopen", _fake_urlopen)

    score = gate._call_sensenova("标题", "摘要", "fake-key")
    assert abs(score - 0.9) < 1e-6
    assert captured["url"].startswith("https://token.sensenova.cn")
    assert captured["model"] == "sensenova-6.8-flash-lite"
    assert captured["has_system"] is True


def test_call_sensenova_network_fail_degrades(gate):
    """_maybe_llm_detect 网络失败时返回 None（不扣分降级）。"""
    # 传 api_key 使 _llm_available=True，但 _call_sensenova 打真实网络失败
    r = gate._maybe_llm_detect("标题", "摘要", provider="sensenova", api_key="fake-key-for-test")
    # 无真实网络 → 应抛异常被 except 捕获返回 None
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
    import os
    os.environ["SENSENOVA_API_KEY"] = "k"  # 保证 _llm_available env 兜底
    from backend.quality.ai_quality_gate import AIQualityGate
    from backend.quality.base import GateContext
    from backend.domain.models import HotspotItem

    g = AIQualityGate()
    # mock _call_sensenova 返回高概率
    monkeypatch.setattr(g, "_call_sensenova", lambda *a, **k: 0.95)
    ctx = GateContext(llm_enabled=True, llm_provider="sensenova", llm_api_key="k")
    item = HotspotItem(
        id="t", title="普通标题", summary="有实质内容的摘要，包含具体信息与结论。",
        source="s", url="https://e.com/1", category="ai",
        published_at="2026-08-20T00:00:00Z", fetched_at="2026-08-20T00:00:00Z",
        is_fallback=False,
    )
    r = g.check(item, ctx)
    assert "llm_ai_generated" in r.flags
    assert r.score_deduction >= 30
    os.environ.pop("SENSENOVA_API_KEY", None)