"""news_alert_service — 资讯告警判定 (spec 2026-09-27 four-modes §2)。

契约:
- match_rules 纯函数: (title, summary, quality_score) → 命中规则 dict 列表
- R3 AI 语境限定: 安全词命中但无 AI 语境词 → 不进 major_ai_security_event
- R2 双信号门槛: 单信号 + quality_score < 75 → 不命中
- config 从 alert_rule_definitions.config JSON 读, 词表可调
"""
import pytest

from backend.services.news_alert_service import (
    match_rules,
    review_candidates,
    run_news_alert_review,
)

CFG = {
    "critical_vuln": {"max_per_run": 5, "keywords": ["在野利用", "0day", "PoC", "紧急补丁"]},
    "major_security_event": {
        "max_per_run": 5,
        "keywords": ["数据泄露", "勒索攻击", "供应链攻击", "APT"],
        "min_signals_alone": 2,
        "quality_score_gate": 75,
    },
    "major_ai_security_event": {
        "max_per_run": 5,
        "keywords": ["提示注入", "模型投毒", "MCP 漏洞"],
        "ai_context_words": ["AI", "LLM", "大模型"],
    },
    "must_know_regulatory": {"max_per_run": 5, "keywords": ["紧急通报", "等保", "报送"]},
}


def _hit(rule):
    return rule["rule"]


class TestMatchRules:
    def test_critical_vuln_single_signal_hits(self):
        hits = match_rules("Chrome 0day 在野利用公开", "详情见原文", 80, CFG)
        assert _hit(hits[0]) == "critical_vuln"

    def test_major_event_two_signals_hits(self):
        hits = match_rules("某厂商遭 APT 数据泄露", "大规模供应链攻击背景", 60, CFG)
        assert any(_hit(h) == "major_security_event" for h in hits)

    def test_major_event_single_signal_low_score_misses(self):
        """R2 门槛: 单信号 + score<75 → 不命中 (降噪声)。"""
        hits = match_rules("某小站数据泄露", "无更多背景", 60, CFG)
        assert not any(_hit(h) == "major_security_event" for h in hits)

    def test_major_event_single_signal_high_score_hits(self):
        hits = match_rules("某厂商数据泄露", "背景", 80, CFG)
        assert any(_hit(h) == "major_security_event" for h in hits)

    def test_ai_event_requires_ai_context(self):
        """R3 限定: 安全词命中但无 AI 语境词 → 不命中。"""
        hits = match_rules("新型提示注入攻击手法", "针对传统 Web 框架", 80, CFG)
        assert not any(_hit(h) == "major_ai_security_event" for h in hits)

    def test_ai_event_with_context_hits(self):
        hits = match_rules("针对 LLM 的新型提示注入攻击", "大模型应用受影响", 80, CFG)
        assert any(_hit(h) == "major_ai_security_event" for h in hits)

    def test_regulatory_hits(self):
        hits = match_rules("网信办发布紧急通报", "等保报送时限调整", 70, CFG)
        assert any(_hit(h) == "must_know_regulatory" for h in hits)

    def test_no_match_returns_empty(self):
        assert match_rules("普通 AI 新闻: 新模型发布", "性能提升", 80, CFG) == []

    def test_hit_carries_matched_signals(self):
        hits = match_rules("Chrome 0day 在野利用公开", "", 80, CFG)
        assert set(hits[0]["signals"]) == {"0day", "在野利用"}


CANDS = [
    {"id": "h1", "rule": "critical_vuln", "signals": ["0day", "在野利用"], "title": "Chrome 0day", "summary": "s"},
    {"id": "h2", "rule": "major_security_event", "signals": ["数据泄露"], "title": "某厂商泄露", "summary": "s"},
]


def _mock_llm(monkeypatch, payload=None, fail=False):
    from backend.services.ai_hub.gateway import llm_service

    async def _gen(prompt, *, task="summary", **kw):
        assert task == "news_alert_review"
        if fail:
            raise RuntimeError("pi down")
        return payload
    monkeypatch.setattr(llm_service, "generate", _gen)


class TestReviewCandidates:
    def test_llm_confirms(self, monkeypatch):
        _mock_llm(monkeypatch, '[{"id": "h1", "execute": true, "reason": "在野利用需排查"}, {"id": "h2", "execute": false}]')
        out = review_candidates(CANDS)
        assert [o["id"] for o in out] == ["h1"]
        assert out[0]["reason"] == "在野利用需排查"

    def test_llm_fail_open_strong_signals_pass(self, monkeypatch):
        """fail-open: LLM 挂 → strength ≥2 的候选直接放行, 单信号丢弃。"""
        _mock_llm(monkeypatch, fail=True)
        out = review_candidates(CANDS)
        assert [o["id"] for o in out] == ["h1"]  # h1 strength=2, h2 strength=1

    def test_llm_garbage_fail_open(self, monkeypatch):
        _mock_llm(monkeypatch, "不是 JSON 的输出")
        out = review_candidates(CANDS)
        assert [o["id"] for o in out] == ["h1"]

    def test_empty_candidates_skips_llm(self, monkeypatch):
        called = {"n": 0}

        async def _gen(prompt, *, task="summary", **kw):
            called["n"] += 1
            return "[]"
        from backend.services.ai_hub.gateway import llm_service
        monkeypatch.setattr(llm_service, "generate", _gen)
        assert review_candidates([]) == []
        assert called["n"] == 0


def _insert_hotspot(item_id, title, summary="", score=80.0, hours_ago=1):
    """插桩 hotspot; source 按 item_id 唯一 — 避开 _trigger_alert 引擎级
    (rule_type+source) 24h 去重, 使 max_per_run 用例只测编排层 cap。"""
    from datetime import datetime, timedelta, timezone

    from backend.repository.db import get_connection
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    get_connection().execute(
        "INSERT OR IGNORE INTO hotspots (id, title, url, source, category,"
        " published_at, quality_score, score, summary, fetched_at, ingested_at)"
        " VALUES (?, ?, ?, ?, 'security', ?, ?, ?, ?, ?, ?)",
        (item_id, title, f"https://t.com/{item_id}", f"测试源-{item_id}",
         ts, score, score, summary, ts, ts),
    )


@pytest.fixture
def review_env(temp_db):
    """temp_db + 4 规则行 + mock LLM 全确认。"""
    from backend.repository.db import close_db, init_db
    close_db()
    init_db()
    from backend.repository.db import get_connection
    get_connection().executescript(open(
        "backend/repository/migrations/128_news_alert_rules.sql", encoding="utf-8"
    ).read())
    yield
    close_db()
    init_db()


class TestRunNewsAlertReview:
    def test_end_to_end_inserts_alert_events(self, review_env, monkeypatch):
        _insert_hotspot("h_a1", "Chrome 0day 在野利用", "需紧急排查", 85)
        _mock_llm(monkeypatch, '[{"id": "h_a1", "execute": true, "reason": "需排查"}]')
        result = run_news_alert_review(lookback_hours=40)
        assert result["alerted"] == 1
        from backend.repository.db import get_connection
        row = get_connection().execute(
            "SELECT * FROM alert_events WHERE item_id = 'h_a1'"
        ).fetchone()
        assert row is not None
        assert row["rule_type"] == "critical_vuln"
        assert row["severity"] == "critical"
        assert "需排查" in row["description"]

    def test_same_hotspot_not_realerted(self, review_env, monkeypatch):
        _insert_hotspot("h_b1", "Chrome 0day 在野利用", "s", 85)
        _mock_llm(monkeypatch, '[{"id": "h_b1", "execute": true, "reason": "r"}]')
        run_news_alert_review(lookback_hours=40)
        result2 = run_news_alert_review(lookback_hours=40)  # 同条目还在窗口内
        assert result2["alerted"] == 0  # 去重闸

    def test_max_per_run_cap(self, review_env, monkeypatch):
        for i in range(7):
            _insert_hotspot(f"h_c{i}", f"漏洞{i} 0day 在野利用", "s", 85)
        _mock_llm(monkeypatch, '[' + ",".join(
            f'{{"id": "h_c{i}", "execute": true, "reason": "r"}}' for i in range(7)
        ) + ']')
        result = run_news_alert_review(lookback_hours=40)
        assert result["alerted"] == 5  # max_per_run

    def test_no_candidates_zero_llm_calls(self, review_env, monkeypatch):
        called = {"n": 0}

        async def _gen(prompt, *, task="summary", **kw):
            called["n"] += 1
            return "[]"
        from backend.services.ai_hub.gateway import llm_service
        monkeypatch.setattr(llm_service, "generate", _gen)
        result = run_news_alert_review(lookback_hours=40)
        assert result == {"candidates": 0, "alerted": 0}
        assert called["n"] == 0

    def test_window_excludes_old_items(self, review_env, monkeypatch):
        _insert_hotspot("h_d1", "Chrome 0day 在野利用", "s", 85, hours_ago=72)
        _mock_llm(monkeypatch, "[]")
        result = run_news_alert_review(lookback_hours=40)
        assert result["candidates"] == 0  # 72h 前的条目不在窗口
