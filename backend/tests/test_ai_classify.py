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
        # 2026-09-19 开闸后 TOML 默认 true, 关 gate 须走 env 覆盖 (优先级高于 TOML)
        monkeypatch.setenv(
            "HOTSPOT_FEATURE_GATES", '{"extensions": {"ai_classify": false}}'
        )
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


class TestClassifyItemsWithAi:
    """P1-2c 主流量批分类: 预算封顶防成本失控 (PRD 风险表), 预算尽诚实 None。"""

    def _item(self, item_id, tags, title="毫无领域线索的标题xyzq"):
        return {"id": item_id, "tags": tags, "title": title, "source_url": ""}

    def _counting_llm(self, monkeypatch, payload='{"domain": "ai"}'):
        """计数桩: 返回 (gen, calls); 每次调用 +1。"""
        calls = {"n": 0}

        async def _gen(prompt, *, task="summary", **kw):
            calls["n"] += 1
            assert task == "ai_classify"
            return payload

        from backend.services.ai_hub.gateway import llm_service
        monkeypatch.setattr(llm_service, "generate", _gen)
        return calls

    def test_budget_caps_llm_calls(self, monkeypatch):
        _enable(monkeypatch)
        calls = self._counting_llm(monkeypatch)
        items = [self._item(f"m{i}", []) for i in range(3)]  # tags=[] 全 miss
        classified, llm_used = ac.classify_items_with_ai(items, max_llm_calls=1)
        # 预算 1 → 恰好 1 次 LLM; 首条增援成功, 其余诚实保留 None 不编造
        assert calls["n"] == 1
        assert llm_used == 1
        assert classified[0]["domain"] == "ai"
        assert classified[1]["domain"] is None
        assert classified[2]["domain"] is None

    def test_rule_hit_saves_budget(self, monkeypatch):
        _enable(monkeypatch)
        calls = self._counting_llm(monkeypatch)
        items = [
            self._item("hit", ["AI"], "某 AI 安全事件"),  # 规则命中 → 零 LLM
            self._item("miss", []),
        ]
        classified, llm_used = ac.classify_items_with_ai(items, max_llm_calls=1)
        # 规则命中不占预算 → 预算 1 全留给 miss 条目
        assert calls["n"] == 1
        assert llm_used == 1
        assert classified[0]["domain"] == "ai"
        assert classified[1]["domain"] == "ai"

    def test_gate_off_zero_llm(self, monkeypatch):
        monkeypatch.setenv(
            "HOTSPOT_FEATURE_GATES", '{"extensions": {"ai_classify": false}}'
        )
        reset_gates()
        calls = self._counting_llm(monkeypatch)
        items = [self._item("m1", []), self._item("m2", ["AI"])]
        classified, llm_used = ac.classify_items_with_ai(items)
        # gate 关 → 等价 batch_classify 语义, 零 LLM 零增援
        assert calls["n"] == 0
        assert llm_used == 0
        assert classified[0]["domain"] is None
        assert classified[1]["domain"] == "ai"

    def test_merge_contract_matches_batch_classify(self, monkeypatch):
        _enable(monkeypatch)
        self._counting_llm(monkeypatch)
        items = [self._item("m1", [])]
        classified, _ = ac.classify_items_with_ai(items, max_llm_calls=1)
        # 合并契约与 batch_classify 同形: 就地补 4 分类键 + topic 派生, id 保留
        d = classified[0]
        assert d["id"] == "m1"
        for key in ("domain", "type", "difficulty", "practice_domain", "topic"):
            assert key in d
