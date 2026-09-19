# backend/tests/test_ai_classify.py
"""ai_classify gate — 纯规则 miss (domain=None) 时 LLM 增援。

契约: classify_item 纯函数零改动; gate 关 → 等价 classify_item;
LLM 失败 / 越权 domain → 兜底纯规则结果; domain 词表严格校验。
"""
import pytest

from backend.extensions import reset_gates
from backend.services import auto_classifier as ac


@pytest.fixture(autouse=True)
def _restore():
    yield
    reset_gates()


def _enable(monkeypatch):
    monkeypatch.setenv(
        "HOTSPOT_FEATURE_GATES", '{"extensions": {"ai_classify": true}}'
    )
    reset_gates()


def _fake_generate(payload=None, fail=False):
    async def _gen(prompt, *, task="summary", **kw):
        assert task == "ai_classify"
        if fail:
            raise RuntimeError("down")
        return payload or ""
    return _gen


def _mock_llm(monkeypatch, payload=None, fail=False):
    from backend.services.ai_hub.gateway import llm_service
    monkeypatch.setattr(llm_service, "generate", _fake_generate(payload, fail))


NO_MATCH = ("完全不相关的标签", "毫无领域线索的标题xyzq", "")


class TestClassifyItemWithAi:
    def test_rule_hit_skips_llm(self, monkeypatch):
        _enable(monkeypatch)
        called = {"n": 0}
        async def _gen(prompt, *, task="summary", **kw):
            called["n"] += 1
            return ""
        from backend.services.ai_hub.gateway import llm_service
        monkeypatch.setattr(llm_service, "generate", _gen)
        result = ac.classify_item_with_ai(["AI"], title="x")
        assert result["domain"] == "ai"
        assert called["n"] == 0  # 规则命中 → 零 LLM

    def test_gate_off_equals_pure(self, monkeypatch):
        monkeypatch.delenv("HOTSPOT_FEATURE_GATES", raising=False)
        reset_gates()
        _mock_llm(monkeypatch, '{"domain":"ai"}')
        r = ac.classify_item_with_ai(*NO_MATCH)
        assert r == ac.classify_item(*NO_MATCH)
        assert r["domain"] is None

    def test_llm_fills_domain(self, monkeypatch):
        _enable(monkeypatch)
        _mock_llm(monkeypatch, '{"domain": "ai", "type": "news", "difficulty": "beginner"}')
        r = ac.classify_item_with_ai(*NO_MATCH)
        assert r["domain"] == "ai"

    def test_llm_invalid_domain_rejected(self, monkeypatch):
        _enable(monkeypatch)
        _mock_llm(monkeypatch, '{"domain": "不存在的域"}')
        r = ac.classify_item_with_ai(*NO_MATCH)
        assert r["domain"] is None

    def test_llm_failure_fallback(self, monkeypatch):
        _enable(monkeypatch)
        _mock_llm(monkeypatch, fail=True)
        r = ac.classify_item_with_ai(*NO_MATCH)
        assert r == ac.classify_item(*NO_MATCH)
