"""v1.7 Phase 3 — AlertService 单元测试.

覆盖:
- evaluate_condition: tag_match (AND/OR/contains_any/all/none)
- evaluate_condition: category_match
- evaluate_condition: keyword_match (title/summary/both)
- _cooldown_ready: 冷却期内/期外/无 last_fired
- evaluate_hotspot: 端到端 (创建规则 → 评估热点 → 触发告警)
- AlertRuleRepository / AlertRepository CRUD
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.config import config
from backend.repository import db
from backend.repository.alerts_repo import AlertRepository, AlertRuleRepository
from backend.repository.hotspot_repo import HotspotRepository
from backend.repository.tags_repo import TagRepository
from backend.services.alert_service import (
    _cooldown_ready,
    evaluate_condition,
    evaluate_hotspot,
)


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_alert_service.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


def _insert_hotspot(hotspot_id: str, title: str, summary: str, category: str = "security") -> None:
    """直接 SQL 插入热点 (绕过 HotspotItem 必填字段)."""
    from datetime import datetime, timezone
    from backend.repository.db import get_connection
    now = datetime.now(timezone.utc).isoformat()
    get_connection().execute(
        """
        INSERT OR REPLACE INTO hotspots
            (id, title, summary, source, url, category, published_at, score,
             fetched_at, is_fallback, quality_score, quality_flags, url_check_status, ingested_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            hotspot_id, title, summary, "test-source",
            f"https://example.com/{hotspot_id}",
            category, now, 50.0, now, 0, 80, "[]", "pending", now,
        ),
    )


# ---------------------------------------------------------------------------
# evaluate_condition — 纯函数测试
# ---------------------------------------------------------------------------
class TestEvaluateConditionTagMatch:
    def test_tag_match_or_contains_any(self):
        cond = {
            "type": "tag_match",
            "operator": "OR",
            "conditions": [{"op": "contains_any", "value": ["cve", "fastapi"]}],
        }
        hotspot = {"tags": ["cve", "vulnerability"]}
        assert evaluate_condition(cond, hotspot) is True

    def test_tag_match_or_no_overlap(self):
        cond = {
            "type": "tag_match",
            "operator": "OR",
            "conditions": [{"op": "contains_any", "value": ["cve", "fastapi"]}],
        }
        hotspot = {"tags": ["llm", "langchain"]}
        assert evaluate_condition(cond, hotspot) is False

    def test_tag_match_and_all_required(self):
        cond = {
            "type": "tag_match",
            "operator": "AND",
            "conditions": [
                {"op": "contains_any", "value": ["cve"]},
                {"op": "contains_any", "value": ["fastapi"]},
            ],
        }
        assert evaluate_condition(cond, {"tags": ["cve", "fastapi"]}) is True
        assert evaluate_condition(cond, {"tags": ["cve"]}) is False

    def test_tag_match_contains_all(self):
        cond = {
            "type": "tag_match",
            "operator": "OR",
            "conditions": [{"op": "contains_all", "value": ["cve", "fastapi"]}],
        }
        assert evaluate_condition(cond, {"tags": ["cve", "fastapi", "llm"]}) is True
        assert evaluate_condition(cond, {"tags": ["cve"]}) is False

    def test_tag_match_contains_none(self):
        cond = {
            "type": "tag_match",
            "operator": "OR",
            "conditions": [{"op": "contains_none", "value": ["cve"]}],
        }
        assert evaluate_condition(cond, {"tags": ["fastapi"]}) is True
        assert evaluate_condition(cond, {"tags": ["cve"]}) is False

    def test_tag_match_empty_tags(self):
        cond = {
            "type": "tag_match",
            "operator": "OR",
            "conditions": [{"op": "contains_any", "value": ["cve"]}],
        }
        assert evaluate_condition(cond, {"tags": []}) is False
        assert evaluate_condition(cond, {}) is False

    def test_tag_match_accepts_json_string_tags(self):
        """hotspot.tags 可能是 JSON 字符串 (来自 hotspots.tags 列)."""
        import json
        cond = {
            "type": "tag_match",
            "operator": "OR",
            "conditions": [{"op": "contains_any", "value": ["cve"]}],
        }
        hotspot = {"tags": json.dumps(["cve", "vulnerability"])}
        assert evaluate_condition(cond, hotspot) is True


class TestEvaluateConditionCategoryMatch:
    def test_category_match_hit(self):
        cond = {"type": "category_match", "value": ["ai", "security"]}
        assert evaluate_condition(cond, {"category": "security"}) is True
        assert evaluate_condition(cond, {"category": "ai"}) is True

    def test_category_match_miss(self):
        cond = {"type": "category_match", "value": ["ai"]}
        assert evaluate_condition(cond, {"category": "security"}) is False

    def test_category_match_accepts_enum(self):
        """category 可能是 Category enum."""
        from backend.domain.enums import Category
        cond = {"type": "category_match", "value": ["security"]}
        assert evaluate_condition(cond, {"category": Category.SECURITY}) is True


class TestEvaluateConditionKeywordMatch:
    def test_keyword_match_title(self):
        cond = {"type": "keyword_match", "value": ["FastAPI"], "field": "title"}
        hotspot = {"title": "FastAPI RCE 漏洞", "summary": "一般描述"}
        assert evaluate_condition(cond, hotspot) is True

    def test_keyword_match_summary(self):
        cond = {"type": "keyword_match", "value": ["勒索"], "field": "summary"}
        hotspot = {"title": "无标题", "summary": "勒索软件攻击"}
        assert evaluate_condition(cond, hotspot) is True

    def test_keyword_match_both_default(self):
        cond = {"type": "keyword_match", "value": ["CVE"]}
        assert evaluate_condition(cond, {"title": "CVE-2024", "summary": "x"}) is True
        assert evaluate_condition(cond, {"title": "x", "summary": "CVE-2024"}) is True
        assert evaluate_condition(cond, {"title": "x", "summary": "y"}) is False

    def test_keyword_match_case_insensitive(self):
        cond = {"type": "keyword_match", "value": ["fastapi"]}
        assert evaluate_condition(cond, {"title": "FastAPI 漏洞", "summary": ""}) is True


class TestEvaluateConditionUnknown:
    def test_unknown_type_returns_false(self):
        assert evaluate_condition({"type": "unknown"}, {"tags": []}) is False


# ---------------------------------------------------------------------------
# _cooldown_ready — 纯函数测试
# ---------------------------------------------------------------------------
class TestCooldownReady:
    def test_no_last_fired_is_ready(self):
        rule = {"last_fired_at": None, "cooldown_sec": 3600}
        assert _cooldown_ready(rule) is True

    def test_within_cooldown_not_ready(self):
        now = datetime.now(timezone.utc)
        rule = {
            "last_fired_at": (now - timedelta(seconds=60)).isoformat(),
            "cooldown_sec": 3600,
        }
        assert _cooldown_ready(rule, now=now) is False

    def test_past_cooldown_ready(self):
        now = datetime.now(timezone.utc)
        rule = {
            "last_fired_at": (now - timedelta(seconds=3700)).isoformat(),
            "cooldown_sec": 3600,
        }
        assert _cooldown_ready(rule, now=now) is True

    def test_invalid_last_fired_ready(self):
        rule = {"last_fired_at": "not-a-date", "cooldown_sec": 3600}
        assert _cooldown_ready(rule) is True


# ---------------------------------------------------------------------------
# AlertRuleRepository CRUD
# ---------------------------------------------------------------------------
class TestAlertRuleRepository:
    def test_add_and_get(self, temp_db):
        repo = AlertRuleRepository()
        repo.add(
            "rule-1", "FastAPI 告警",
            {"type": "tag_match", "operator": "OR", "conditions": [{"op": "contains_any", "value": ["fastapi"]}]},
            {"type": "sse"},
            cooldown_sec=1800,
        )
        got = repo.get("rule-1")
        assert got is not None
        assert got["name"] == "FastAPI 告警"
        assert got["cooldown_sec"] == 1800
        assert got["enabled"] is True
        assert got["condition"]["type"] == "tag_match"
        assert got["action"]["type"] == "sse"

    def test_list_enabled(self, temp_db):
        repo = AlertRuleRepository()
        repo.add("r-enabled", "A", {"type": "tag_match", "conditions": []}, {}, enabled=True)
        repo.add("r-disabled", "B", {"type": "tag_match", "conditions": []}, {}, enabled=False)
        enabled = repo.list_enabled()
        assert len(enabled) == 1
        assert enabled[0]["id"] == "r-enabled"

    def test_update(self, temp_db):
        repo = AlertRuleRepository()
        repo.add("r-upd", "Original", {"type": "tag_match", "conditions": []}, {}, cooldown_sec=3600)
        updated = repo.update("r-upd", name="Renamed", cooldown_sec=600, enabled=False)
        assert updated["name"] == "Renamed"
        assert updated["cooldown_sec"] == 600
        assert updated["enabled"] is False

    def test_touch_last_fired(self, temp_db):
        repo = AlertRuleRepository()
        repo.add("r-touch", "T", {"type": "tag_match", "conditions": []}, {})
        assert repo.get("r-touch")["last_fired_at"] is None
        repo.touch_last_fired("r-touch", "2026-07-23T00:00:00+00:00")
        assert repo.get("r-touch")["last_fired_at"] == "2026-07-23T00:00:00+00:00"

    def test_delete(self, temp_db):
        repo = AlertRuleRepository()
        repo.add("r-del", "D", {"type": "tag_match", "conditions": []}, {})
        assert repo.delete("r-del") == 1
        assert repo.get("r-del") is None


# ---------------------------------------------------------------------------
# AlertRepository CRUD
# ---------------------------------------------------------------------------
class TestAlertRepository:
    def _ensure_rule(self, rule_id: str = "rule-1"):
        """外键约束: alerts.rule_id 必须先在 alert_rules 表存在."""
        AlertRuleRepository().add(rule_id, "测试规则", {"type": "tag_match", "conditions": []}, {})

    def test_add_and_get(self, temp_db):
        self._ensure_rule()
        repo = AlertRepository()
        alert = repo.add("rule-1", "hotspot", "h-1", {"title": "x"})
        assert alert["rule_id"] == "rule-1"
        assert alert["entity_type"] == "hotspot"
        assert alert["entity_id"] == "h-1"
        assert alert["status"] == "pending"
        assert alert["payload"]["title"] == "x"
        got = repo.get(alert["id"])
        assert got is not None
        assert got["id"] == alert["id"]

    def test_list_by_status(self, temp_db):
        self._ensure_rule()
        repo = AlertRepository()
        a1 = repo.add("rule-1", "hotspot", "h-1")
        a2 = repo.add("rule-1", "hotspot", "h-2")
        repo.mark_read(a1["id"])
        pending = repo.list(status="pending")
        read = repo.list(status="read")
        assert len(pending) == 1
        assert pending[0]["id"] == a2["id"]
        assert len(read) == 1
        assert read[0]["id"] == a1["id"]

    def test_mark_read(self, temp_db):
        self._ensure_rule()
        repo = AlertRepository()
        a = repo.add("rule-1", "hotspot", "h-1")
        updated = repo.mark_read(a["id"])
        assert updated["status"] == "read"
        assert updated["processed_at"] is not None

    def test_mark_read_missing_returns_none(self, temp_db):
        assert AlertRepository().mark_read("no-such") is None

    def test_delete(self, temp_db):
        self._ensure_rule()
        repo = AlertRepository()
        a = repo.add("rule-1", "hotspot", "h-1")
        assert repo.delete(a["id"]) == 1
        assert repo.get(a["id"]) is None

    def test_count(self, temp_db):
        self._ensure_rule()
        repo = AlertRepository()
        repo.add("rule-1", "hotspot", "h-1")
        repo.add("rule-1", "hotspot", "h-2")
        assert repo.count() == 2
        assert repo.count(status="pending") == 2


# ---------------------------------------------------------------------------
# evaluate_hotspot — 端到端集成
# ---------------------------------------------------------------------------
class TestEvaluateHotspot:
    def test_matching_rule_fires_alert(self, temp_db):
        """验收 1 核心: 匹配的规则触发告警."""
        # 1. 插入热点
        _insert_hotspot("h-alert-1", "FastAPI RCE 漏洞", "FastAPI 框架 RCE")
        # 2. 给热点打 fastapi 标签
        TagRepository().add("fastapi", "FastAPI", "framework")
        TagRepository().attach("h-alert-1", "fastapi", 0.8)
        # 3. 创建规则
        AlertRuleRepository().add(
            "rule-fastapi", "FastAPI 告警",
            {"type": "tag_match", "operator": "OR",
             "conditions": [{"op": "contains_any", "value": ["fastapi"]}]},
            {"type": "sse"},
        )
        # 4. 评估
        fired = evaluate_hotspot("h-alert-1")
        assert fired == ["rule-fastapi"]
        # 5. 告警已写入
        alerts = AlertRepository().list(rule_id="rule-fastapi")
        assert len(alerts) == 1
        assert alerts[0]["entity_id"] == "h-alert-1"

    def test_no_matching_rule_no_alert(self, temp_db):
        _insert_hotspot("h-no-match", "普通文章", "无标签")
        AlertRuleRepository().add(
            "rule-cve", "CVE 告警",
            {"type": "tag_match", "operator": "OR",
             "conditions": [{"op": "contains_any", "value": ["cve"]}]},
            {},
        )
        fired = evaluate_hotspot("h-no-match")
        assert fired == []
        assert AlertRepository().count() == 0

    def test_cooldown_prevents_refire(self, temp_db):
        """cooldown 期内不重复触发."""
        _insert_hotspot("h-cool-1", "FastAPI 漏洞", "FastAPI RCE")
        _insert_hotspot("h-cool-2", "FastAPI 另一漏洞", "FastAPI 注入")
        TagRepository().add("fastapi", "FastAPI", "framework")
        TagRepository().attach("h-cool-1", "fastapi", 0.8)
        TagRepository().attach("h-cool-2", "fastapi", 0.8)
        AlertRuleRepository().add(
            "rule-cool", "FastAPI 告警",
            {"type": "tag_match", "operator": "OR",
             "conditions": [{"op": "contains_any", "value": ["fastapi"]}]},
            {},
            cooldown_sec=3600,
        )
        # 第一次触发
        assert evaluate_hotspot("h-cool-1") == ["rule-cool"]
        # 第二次 (同规则, cooldown 内) 不应触发
        assert evaluate_hotspot("h-cool-2") == []
        # 仍只有 1 条告警 (cooldown 阻止了第二次)
        assert len(AlertRepository().list(rule_id="rule-cool")) == 1

    def test_missing_hotspot_returns_empty(self, temp_db):
        assert evaluate_hotspot("no-such-hotspot") == []

    def test_multiple_rules_fire_independently(self, temp_db):
        """多条规则同时匹配, 各自触发."""
        _insert_hotspot("h-multi", "FastAPI CVE-2024 漏洞", "FastAPI 框架 CVE")
        TagRepository().add("fastapi", "FastAPI", "framework")
        TagRepository().add("cve", "CVE", "cve")
        TagRepository().attach("h-multi", "fastapi", 0.8)
        TagRepository().attach("h-multi", "cve", 1.0)
        AlertRuleRepository().add(
            "r-fastapi", "FastAPI 告警",
            {"type": "tag_match", "operator": "OR",
             "conditions": [{"op": "contains_any", "value": ["fastapi"]}]},
            {},
        )
        AlertRuleRepository().add(
            "r-cve", "CVE 告警",
            {"type": "tag_match", "operator": "OR",
             "conditions": [{"op": "contains_any", "value": ["cve"]}]},
            {},
        )
        fired = evaluate_hotspot("h-multi")
        assert set(fired) == {"r-fastapi", "r-cve"}
        assert AlertRepository().count() == 2

    def test_disabled_rule_not_evaluated(self, temp_db):
        _insert_hotspot("h-disabled", "FastAPI 漏洞", "FastAPI RCE")
        TagRepository().add("fastapi", "FastAPI", "framework")
        TagRepository().attach("h-disabled", "fastapi", 0.8)
        AlertRuleRepository().add(
            "r-disabled", "禁用规则",
            {"type": "tag_match", "operator": "OR",
             "conditions": [{"op": "contains_any", "value": ["fastapi"]}]},
            {},
            enabled=False,
        )
        assert evaluate_hotspot("h-disabled") == []

    def test_keyword_rule_fires(self, temp_db):
        """keyword_match 规则也能触发."""
        _insert_hotspot("h-kw", "勒索软件攻击事件", "某公司遭勒索")
        AlertRuleRepository().add(
            "r-ransom", "勒索告警",
            {"type": "keyword_match", "value": ["勒索"], "field": "both"},
            {},
        )
        fired = evaluate_hotspot("h-kw")
        assert fired == ["r-ransom"]

    def test_category_rule_fires(self, temp_db):
        """category_match 规则也能触发."""
        _insert_hotspot("h-cat", "AI 突破", "AI 进展", category="ai")
        AlertRuleRepository().add(
            "r-ai", "AI 告警",
            {"type": "category_match", "value": ["ai"]},
            {},
        )
        fired = evaluate_hotspot("h-cat")
        assert fired == ["r-ai"]
