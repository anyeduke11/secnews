"""语义门禁 (gate semantic_filter) — info_filter 规则 neutral 时的 LLM verdict 判别。

契约: 仅 neutral 触发; verdict=reject → drop; LLM 失败/解析失败 →
fail-open 保留 (门禁故障不丢内容); gate 关 → 零 LLM 调用行为不变。
"""
import pytest

from backend.extensions import reset_gates
from backend.services import info_filter_gate
from backend.services.ai_hub import tasks as ai_tasks
from backend.services.ai_hub.gateway import llm_service


@pytest.fixture(autouse=True)
def _gate_toggle():
    yield
    reset_gates()


def _enable(monkeypatch):
    monkeypatch.setenv(
        "HOTSPOT_FEATURE_GATES", '{"extensions": {"info_filter": true, "semantic_filter": true}}'
    )
    reset_gates()


def _neutral_rules(monkeypatch):
    monkeypatch.setattr(info_filter_gate, "_load_rules_cached", lambda: [{"id": 1}])
    import backend.services.info_filter_service as svc
    monkeypatch.setattr(svc, "evaluate", lambda rules, **kw: ("neutral", None))


def _fake_generate(payload: str, fail: bool = False):
    async def _gen(prompt, *, task="summary", **kw):
        assert task == "semantic_filter"
        if fail:
            raise RuntimeError("all providers failed")
        return payload
    return _gen


ITEM = {"source_name": "测试源", "title": "标题", "summary": "摘要"}


class TestSemanticVerdict:
    def test_parse_allow(self, monkeypatch):
        monkeypatch.setattr(
            llm_service, "generate", _fake_generate('{"verdict":"allow","reason":"ok"}'),
        )
        assert ai_tasks.semantic_verdict("内容")["verdict"] == "allow"

    def test_parse_reject(self, monkeypatch):
        monkeypatch.setattr(
            llm_service, "generate", _fake_generate('前置噪声 {"verdict":"reject","reason":"广告"} 尾部'),
        )
        assert ai_tasks.semantic_verdict("内容")["verdict"] == "reject"

    def test_parse_failure_fail_open(self, monkeypatch):
        monkeypatch.setattr(
            llm_service, "generate", _fake_generate("不是 JSON"),
        )
        assert ai_tasks.semantic_verdict("内容")["verdict"] == "allow"

    def test_llm_failure_fail_open(self, monkeypatch):
        monkeypatch.setattr(
            llm_service, "generate", _fake_generate("", fail=True),
        )
        assert ai_tasks.semantic_verdict("内容")["verdict"] == "allow"


class TestFilterItemsSemanticLayer:
    def test_gate_off_no_llm(self, monkeypatch):
        # 2026-09-19 开闸后 TOML 默认 true, 关 gate 须走 env 覆盖 (优先级高于 TOML)
        monkeypatch.setenv(
            "HOTSPOT_FEATURE_GATES", '{"extensions": {"semantic_filter": false}}'
        )
        reset_gates()
        _neutral_rules(monkeypatch)
        called = {"n": 0}
        monkeypatch.setattr(
            llm_service, "generate",
            async_fail_counter(called),
        )
        kept = info_filter_gate.filter_items([ITEM])
        assert kept == [ITEM]
        assert called["n"] == 0

    def test_reject_dropped(self, monkeypatch):
        _enable(monkeypatch)
        _neutral_rules(monkeypatch)
        monkeypatch.setattr(
            llm_service, "generate",
            _fake_generate('{"verdict":"reject","reason":"广告"}'),
        )
        kept = info_filter_gate.filter_items(
            [ITEM, {"source_name": "s", "title": "t2", "summary": "", "_x": 1}]
        )
        # 第二条同样 reject → 全 drop
        assert kept == []

    def test_allow_kept(self, monkeypatch):
        _enable(monkeypatch)
        _neutral_rules(monkeypatch)
        monkeypatch.setattr(
            llm_service, "generate",
            _fake_generate('{"verdict":"allow","reason":"ok"}'),
        )
        assert info_filter_gate.filter_items([ITEM]) == [ITEM]

    def test_llm_error_fail_open(self, monkeypatch):
        _enable(monkeypatch)
        _neutral_rules(monkeypatch)
        monkeypatch.setattr(
            llm_service, "generate",
            async_fail_counter({"n": 0}, fail=True),
        )
        assert info_filter_gate.filter_items([ITEM]) == [ITEM]


def async_fail_counter(called, fail=False):
    async def _gen(prompt, *, task="summary", **kw):
        called["n"] += 1
        if fail:
            raise RuntimeError("down")
        return '{"verdict":"allow","reason":"ok"}'
    return _gen
