"""语义门禁 (gate semantic_filter) — 判别契约 + post-ingest 补偿面 (v0.8.7 P3-F)。

契约: semantic_verdict fail-open 可见 (D2 loop 检测兜底); 采集热路径
(filter_items) 零 LLM; 判别在 tick 尾 post_ingest_semantic_filter 异步
补偿 — reject → is_hidden=1 + flag 打标 (可回溯), LLM 失败不打标下轮重试。
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

    def test_loop_thread_fail_open_visible(self, monkeypatch, temp_db):
        """DEV-0287 (D2): loop 线程调用 → 跳过 LLM + 显式 outcome (不再静默)。

        采集链 collect(loop) → filter_items → semantic_verdict 曾在运行中
        loop 上 asyncio.run → RuntimeError 被吞 → 静默 fail-open +
        'coroutine never awaited' 噪声。契约: 返回 allow 语义不变,
        但必须落 llm_usage_log ok=0 (error=event_loop_thread) + 错误环。
        """
        import asyncio

        from backend.repository.db import get_connection
        from backend.services.ai_hub.usage import recent_llm_errors

        calls = []

        async def _must_not_call(prompt, **kw):  # pragma: no cover — 不应到达
            calls.append(prompt)
            return "{}"

        monkeypatch.setattr(llm_service, "generate", _must_not_call)

        async def _in_loop():
            return ai_tasks.semantic_verdict("内容")

        sv = asyncio.run(_in_loop())
        assert sv == {"verdict": "allow", "reason": "event_loop_thread_fail_open"}
        assert not calls, "loop 线程上不得发起 LLM 调用"
        row = get_connection().execute(
            "SELECT ok, error FROM llm_usage_log WHERE scene='semantic_filter' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None and row[0] == 0 and "event_loop_thread" in row[1]
        assert any(e["task"] == "semantic_filter" for e in recent_llm_errors())

    def test_non_loop_thread_still_runs_llm(self, monkeypatch):
        """非 loop 线程 (脚本/任务队列) → asyncio.run 语义不变, LLM 正常调用。"""
        monkeypatch.setattr(
            llm_service, "generate", _fake_generate('{"verdict":"reject","reason":"r"}'),
        )
        assert ai_tasks.semantic_verdict("内容")["verdict"] == "reject"


class TestFilterItemsHotPath:
    """v0.8.7 P3-F: filter_items 热路径已摘除语义 LLM 判别 (纯规则 Layer 2)。"""

    def test_no_llm_call_even_when_gates_on(self, monkeypatch):
        """回归守卫: 判别若回流热路径, loop 线程 D2 fail-open + 本断言双保险。"""
        _enable(monkeypatch)
        _neutral_rules(monkeypatch)
        called = {"n": 0}
        monkeypatch.setattr(
            llm_service, "generate",
            async_fail_counter(called),
        )
        assert info_filter_gate.filter_items([ITEM]) == [ITEM]
        assert called["n"] == 0


class TestPostIngestSemanticFilter:
    """post-ingest 补偿判别 (tick 尾 to_thread, 无 running loop → 真调 LLM)。"""

    def _seed(self, hotspot_id: str, *, fetched_hours_ago: float = 1.0) -> None:
        from datetime import datetime, timedelta, timezone

        from backend.repository.db import get_connection

        conn = get_connection()
        fetched = (
            datetime.now(timezone.utc) - timedelta(hours=fetched_hours_ago)
        ).isoformat()
        conn.execute(
            "INSERT OR IGNORE INTO hotspots "
            "(id, title, summary, source, url, category, published_at, fetched_at) "
            "VALUES (?, ?, '摘要', '测试源', ?, 'security', ?, ?)",
            (hotspot_id, f"标题{hotspot_id}",
             f"https://example.com/{hotspot_id}", fetched, fetched),
        )
        conn.commit()

    def _row(self, hotspot_id: str):
        import json

        from backend.repository.db import get_connection

        r = get_connection().execute(
            "SELECT is_hidden, quality_flags FROM hotspots WHERE id = ?",
            (hotspot_id,),
        ).fetchone()
        return r[0], json.loads(r[1] or "[]")

    def test_semantic_gate_off_skips(self, monkeypatch, temp_db):
        """semantic_filter gate 关 → 零候选读 + 零 LLM (显式 skipped_reason)。"""
        self._seed("pf_off")
        called = {"n": 0}
        monkeypatch.setattr(
            llm_service, "generate", async_fail_counter(called),
        )
        summary = info_filter_gate.post_ingest_semantic_filter()
        assert summary["skipped_reason"] == "semantic_filter_gate_off"
        assert summary["judged"] == 0 and called["n"] == 0
        assert self._row("pf_off")[0] == 0  # is_hidden 不变

    def test_reject_hidden_and_flagged_idempotent(self, monkeypatch, temp_db):
        """reject → is_hidden=1 + semantic_checked/semantic_reject 双 flag; 重复轮不重判。"""
        self._seed("pf_rej")
        _enable(monkeypatch)
        monkeypatch.setattr(
            llm_service, "generate",
            _fake_generate('{"verdict":"reject","reason":"广告"}'),
        )
        summary = info_filter_gate.post_ingest_semantic_filter()
        assert summary["judged"] == 1 and summary["rejected"] == 1
        hidden, flags = self._row("pf_rej")
        assert hidden == 1
        assert "semantic_checked" in flags and "semantic_reject" in flags

        # 幂等: 已打标条目不再进候选
        called = {"n": 0}
        monkeypatch.setattr(
            llm_service, "generate", async_fail_counter(called),
        )
        summary2 = info_filter_gate.post_ingest_semantic_filter()
        assert summary2["candidates"] == 0 and called["n"] == 0

    def test_allow_checked_not_hidden(self, monkeypatch, temp_db):
        """allow → 只打 semantic_checked, 不隐藏 (判别留痕 ≠ 拒绝)。"""
        self._seed("pf_ok")
        _enable(monkeypatch)
        monkeypatch.setattr(
            llm_service, "generate",
            _fake_generate('{"verdict":"allow","reason":"ok"}'),
        )
        summary = info_filter_gate.post_ingest_semantic_filter()
        assert summary["judged"] == 1 and summary["rejected"] == 0
        hidden, flags = self._row("pf_ok")
        assert hidden == 0 and "semantic_checked" in flags

    def test_fail_open_not_checked_retries_next_tick(self, monkeypatch, temp_db):
        """LLM 失败 fail-open → 不打标 (下轮重试), 计入 errors 不计入 judged。"""
        self._seed("pf_fail")
        _enable(monkeypatch)
        monkeypatch.setattr(
            llm_service, "generate",
            _fake_generate("", fail=True),
        )
        summary = info_filter_gate.post_ingest_semantic_filter()
        assert summary["judged"] == 0 and summary["errors"] == 1
        hidden, flags = self._row("pf_fail")
        assert hidden == 0 and "semantic_checked" not in flags


def async_fail_counter(called, fail=False):
    async def _gen(prompt, *, task="summary", **kw):
        called["n"] += 1
        if fail:
            raise RuntimeError("down")
        return '{"verdict":"allow","reason":"ok"}'
    return _gen
