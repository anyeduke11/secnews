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
    monkeypatch.setattr(ai_mod.AIService, "_resolve_api_key", lambda self, provider=None: "")
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
    monkeypatch.setattr(AIService, "_resolve_api_key", lambda self, provider=None: "fake-key")
    monkeypatch.setattr(AIService, "_resolve_provider", staticmethod(lambda: "sensenova"))
    monkeypatch.setattr(
        "httpx.Client.post",
        lambda *a, **k: (_ for _ in ()).throw(ConnectionError("no network")),
    )
    r = svc.gate_detect("标题", "摘要")
    assert r is None


# ── v0.8.6 P2-1 (G2①): gate_detect 显式 outcome ────────────────────
# 审计基线: sensenova ReadTimeout ~1,006 次/日只进分散 WARNING, llm_usage_log
# 零痕迹 → G2① 静默失败。契约: 三类 None 路径 (异常/限频/provider 不可用) 与
# 成功路径全部经 _record 落 llm_usage_log; 返回值语义不变 (失败仍 None fail-open)。


def _patch_gate_happy_config(monkeypatch):
    """公共底座: provider=sensenova 可用 + 密钥就绪 (失败注入由各用例自定)。"""
    from backend.services.ai_hub import AIService

    monkeypatch.setattr(AIService, "_resolve_provider", staticmethod(lambda: "sensenova"))
    monkeypatch.setattr(AIService, "available", lambda self, p=None: True)
    monkeypatch.setattr(AIService, "_resolve_api_key", lambda self, provider=None: "fake-key")


def test_gate_detect_timeout_records_failure_outcome(monkeypatch):
    """超时用例 → _record ok=False + error 透传, fail-open 返回 None 不变。"""
    from backend.services.ai_hub import AIService

    svc = AIService()
    _patch_gate_happy_config(monkeypatch)
    monkeypatch.setattr(
        AIService, "_call_sensenova_detect",
        lambda *a, **k: (_ for _ in ()).throw(TimeoutError("The read operation timed out")),
    )
    record_calls: list[tuple] = []
    monkeypatch.setattr(
        AIService, "_record",
        lambda self, provider, model, task, *, ok, error=None, **_:
            record_calls.append((provider, task, ok, error)),
    )
    r = svc.gate_detect("标题", "摘要")
    assert r is None, "fail-open 语义必须保持 (P0-12 裁决)"
    assert len(record_calls) == 1, f"期望恰好 1 次失败记账, 实得 {record_calls}"
    provider, task, ok, error = record_calls[0]
    assert provider == "sensenova" and task == "gate_detect"
    assert ok is False and "TimeoutError" in (error or "")


def test_gate_detect_rate_limited_records_outcome(monkeypatch):
    """限频拒绝 → _record ok=False error='rate_limited' (预算水位可见)。"""
    from backend.services.ai_hub import AIService

    svc = AIService()
    _patch_gate_happy_config(monkeypatch)
    monkeypatch.setattr(AIService, "gate_rate_allowed", lambda self: False)
    record_calls: list[tuple] = []
    monkeypatch.setattr(
        AIService, "_record",
        lambda self, provider, model, task, *, ok, error=None, **_:
            record_calls.append((task, ok, error)),
    )
    r = svc.gate_detect("标题", "摘要")
    assert r is None
    assert record_calls == [("gate_detect", False, "rate_limited")]


def test_gate_detect_provider_unavailable_records_outcome(monkeypatch):
    """provider 不可用 → _record ok=False error='provider_unavailable'
    (AI 全静默时最危险的隐形失败, 此前完全不可见)。"""
    from backend.services.ai_hub import AIService

    svc = AIService()
    monkeypatch.setattr(AIService, "_resolve_provider", staticmethod(lambda: "sensenova"))
    monkeypatch.setattr(AIService, "available", lambda self, p=None: False)
    record_calls: list[tuple] = []
    monkeypatch.setattr(
        AIService, "_record",
        lambda self, provider, model, task, *, ok, error=None, **_:
            record_calls.append((task, ok, error)),
    )
    r = svc.gate_detect("标题", "摘要")
    assert r is None
    assert record_calls == [("gate_detect", False, "provider_unavailable")]


def test_gate_detect_success_records_usage(monkeypatch):
    """成功路径同批记账 (与 evaluate 成败双记契约一致) — 否则
    success_stats 成功率分母失真 (只有失败行会拖低全局成功率)。"""
    from backend.services.ai_hub import AIService

    svc = AIService()
    _patch_gate_happy_config(monkeypatch)
    monkeypatch.setattr(AIService, "_call_sensenova_detect", lambda *a, **k: 0.9)
    record_calls: list[tuple] = []
    monkeypatch.setattr(
        AIService, "_record",
        lambda self, provider, model, task, *, ok, **_:
            record_calls.append((task, ok)),
    )
    r = svc.gate_detect("标题", "摘要")
    assert abs(r - 0.9) < 1e-6
    assert record_calls == [("gate_detect", True)]


def test_gate_detect_failure_lands_in_llm_usage_log(temp_db, monkeypatch):
    """P2-1 验收真值: 超时 → llm_usage_log 实落 ok=0 行 (scene=gate_detect),
    且 success_stats.fails_by_scene_24h 可聚合 (G2① 清零确认的查询面)。"""
    from backend.repository.db import get_connection
    from backend.services.ai_hub import AIService
    from backend.services.ai_hub.usage import success_stats_24h

    svc = AIService()
    _patch_gate_happy_config(monkeypatch)
    monkeypatch.setattr(
        AIService, "_call_sensenova_detect",
        lambda *a, **k: (_ for _ in ()).throw(TimeoutError("The read operation timed out")),
    )
    assert svc.gate_detect("标题", "摘要") is None
    row = get_connection().execute(
        "SELECT ok, error, scene FROM llm_usage_log WHERE scene = 'gate_detect'"
    ).fetchone()
    assert row is not None, "llm_usage_log 必须有 gate_detect 行 (outcome≠ok)"
    assert row["ok"] == 0 and "TimeoutError" in (row["error"] or "")
    stats = success_stats_24h()
    assert stats["fails_by_scene_24h"].get("gate_detect") == 1


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