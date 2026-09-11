"""DEV-0176 T0.5 — SK-01 每日优先级摘要按实践域分区测试。

纯单元测试: monkeypatch _query_admission_recent / _query_signals_recent /
_query_interest_domains, 不依赖 DB / dsh / ai_hub。

覆盖:
- 无画像: practice_partitions 为 None (单组渲染 = 现状), top_items 仍附加 practice_domain
- 有画像: 命中域分组 + 其余归 other (降权不删), interest_domains 回显
- fallback_no_data: 分区 None + interest 回显
"""
from __future__ import annotations

import json

import pytest

from backend.services.skill_registry import sk01_daily_priority as sk01
from backend.services.skill_registry.sk01_daily_priority import DailyPriorityIntelService

_RAW_DSH = json.dumps({
    "top_items": [
        {"title": "等保 2.0 三级测评要点解读"},
        {"title": "CVE-2026-1234 漏洞复现与分析"},
        {"title": "央行发布年度支付体系报告"},
    ],
    "watchlist_changes": [],
    "suggested_actions": ["关注 CVE-2026-1234 补丁进展"],
}, ensure_ascii=False)

_ADMISSION_ROW = [{"action": "allow", "verdict": "allow", "subject_id": "S1", "reason": "r", "ts": "2026-09-12"}]
_SIGNAL_ROW = [{"id": "SIG1", "subject_id": "S1", "confidence": 0.9, "summary": "测试信号", "occurred_at": "2026-09-12"}]


@pytest.fixture
def service():
    # dsh 调用注入固定返回 (不真调 dsh/ai_hub); receipt best-effort 失败被吞
    return DailyPriorityIntelService(dsh_caller=lambda _prompt: _RAW_DSH)


def _wire_queries(monkeypatch: pytest.MonkeyPatch, *, admission: list, signals: list, interests: list[str]) -> None:
    monkeypatch.setattr(sk01, "_query_admission_recent", lambda days=7: admission)
    monkeypatch.setattr(sk01, "_query_signals_recent", lambda days=3: signals)
    monkeypatch.setattr(sk01, "_query_interest_domains", lambda: interests)
    # watchlist 走 settings.kv, 一并注入避免 DB 依赖
    monkeypatch.setattr(sk01, "_query_watchlist", lambda: [])


class TestSk01PracticePartitions:
    def test_no_interest_single_group_and_domains_attached(self, service, monkeypatch):
        _wire_queries(monkeypatch, admission=_ADMISSION_ROW, signals=_SIGNAL_ROW, interests=[])
        result = service.compute()
        assert result["mode"] == "dsh"
        assert result["interest_domains"] == []
        assert result["practice_partitions"] is None, "无画像应单组渲染 (= 现状)"
        by_title = {it["title"]: it["practice_domain"] for it in result["top_items"]}
        assert by_title["CVE-2026-1234 漏洞复现与分析"] == "vuln_research"
        assert by_title["等保 2.0 三级测评要点解读"] == "compliance"
        assert by_title["央行发布年度支付体系报告"] is None

    def test_with_interest_partitions_and_other(self, service, monkeypatch):
        _wire_queries(monkeypatch, admission=_ADMISSION_ROW, signals=_SIGNAL_ROW,
                      interests=["vuln_research", "compliance"])
        result = service.compute()
        parts = result["practice_partitions"]
        assert result["interest_domains"] == ["vuln_research", "compliance"]
        assert parts is not None
        assert [it["title"] for it in parts["vuln_research"]] == ["CVE-2026-1234 漏洞复现与分析"]
        assert [it["title"] for it in parts["compliance"]] == ["等保 2.0 三级测评要点解读"]
        assert [it["title"] for it in parts["other"]] == ["央行发布年度支付体系报告"], "未命中不删除"

    def test_fallback_no_data_still_echoes_interest(self, service, monkeypatch):
        _wire_queries(monkeypatch, admission=[], signals=[], interests=["appsec"])
        result = service.compute()
        assert result["mode"] == "fallback_no_data"
        assert result["top_items"] == []
        assert result["interest_domains"] == ["appsec"]
        assert result["practice_partitions"] is None
