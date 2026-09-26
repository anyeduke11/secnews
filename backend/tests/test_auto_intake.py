"""自动入管规则引擎测试 (2026-09-26, design docs/superpowers/specs/2026-09-26-auto-intake-design.md)。

覆盖 (计划 Task 1 验收):
- 开关关闭零动作 (默认 enabled=false, gate 不新增 — kv enabled)
- 每日上限截断 (第一轮 LIMIT 截断, 第二轮 limit_reached 拦截)
- 质量阈值过滤 (quality_score < min_quality_score 不入管)
- 域命中过滤 (命中入管 / 未命中跳过; require_domain_hit=False 全放行)
- 游标防重扫 + 首跑不回填历史 (游标 = 当前时刻)
- promote 扩展字段落 md (content=正文 / category=frontmatter / source 通道),
  收藏默认调用零变化 (source='secnews', 无 category 字段)

执行: .venv/bin/python3 -m pytest backend/tests/test_auto_intake.py -v
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.config import config
from backend.repository import db
from backend.repository.db import get_connection
from backend.repository.knowledge_repo import knowledge_repo
from backend.repository.settings_repo import SettingsRepository
from backend.services import sag_service
from backend.services.auto_intake_service import (
    CURSOR_KEY,
    get_auto_intake_config,
    run_auto_intake,
)
from backend.services.data_cleaning import item_id_from_url
from backend.services.settings_service import SettingsService


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """隔离 DB 到 tmp_path (全量 migration; md 写入由 conftest autouse 重定向 wiki 根)。"""
    test_db = tmp_path / "test_auto_intake.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


def _insert_hotspot(
    hid: str,
    *,
    title: str = "item",
    summary: str = "summary text",
    tags: str = "[]",
    quality_score: int = 100,
    ingested_at: str | None = None,
    category: str = "security",
) -> None:
    now = datetime.now(timezone.utc)
    get_connection().execute(
        """
        INSERT INTO hotspots (
            id, title, summary, source, url, category,
            published_at, score, fetched_at, is_fallback,
            quality_score, quality_flags, ingested_at, tags
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            hid,
            title,
            summary,
            "test",
            f"https://example.com/{hid}",
            category,
            now.isoformat(),
            50,
            now.isoformat(),
            0,
            quality_score,
            "[]",
            ingested_at or now.isoformat(),
            tags,
        ),
    )


def _enable(**overrides) -> None:
    """打开开关 (经 SettingsService → 前缀契约 + audit), 可覆盖其余配置。"""
    SettingsService().set("knowledge.auto_intake.enabled", True)
    for key, value in overrides.items():
        SettingsService().set(f"knowledge.auto_intake.{key}", value)


def _set_cursor_past(minutes: int = 60) -> None:
    """游标拨到过去 — 模拟"系统已运行过一轮" (绕过首跑=now 不回填语义)。"""
    past = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    SettingsRepository().set(CURSOR_KEY, past)


# ---------------------------------------------------------------------------
# 配置读取
# ---------------------------------------------------------------------------
class TestConfig:
    def test_defaults(self, temp_db):
        """默认: 关闭 / 阈值 85 / 上限 20 / 要求域命中 (design §3.1)。"""
        assert get_auto_intake_config() == {
            "enabled": False,
            "min_quality_score": 85,
            "daily_limit": 20,
            "require_domain_hit": True,
        }

    def test_roundtrip_after_write(self, temp_db):
        _enable(min_quality_score=70, daily_limit=5)
        cfg = get_auto_intake_config()
        assert cfg["enabled"] is True
        assert cfg["min_quality_score"] == 70
        assert cfg["daily_limit"] == 5


# ---------------------------------------------------------------------------
# 六步评估流程
# ---------------------------------------------------------------------------
class TestRunAutoIntake:
    def test_disabled_noop(self, temp_db):
        """开关关闭 → 零动作, 不写任何 knowledge item。"""
        _insert_hotspot("h1", quality_score=99)
        result = run_auto_intake()
        assert result == {
            "evaluated": 0,
            "intaken": 0,
            "skipped_domain": 0,
            "limit_reached": False,
        }
        assert knowledge_repo.count_items() == 0

    def test_quality_threshold_filters(self, temp_db):
        """质量阈值: ≥ min_quality_score 入管, 低于跳过 (design 步骤 3)。"""
        _enable(min_quality_score=85)
        _set_cursor_past()
        _insert_hotspot("hq", quality_score=90)
        _insert_hotspot("hl", quality_score=84)
        result = run_auto_intake()
        assert result["evaluated"] == 1
        assert result["intaken"] == 1
        assert knowledge_repo.get_item(item_id_from_url("https://example.com/hq")) is not None
        assert knowledge_repo.get_item(item_id_from_url("https://example.com/hl")) is None

    def test_daily_limit_truncates_then_blocks(self, temp_db):
        """每日上限: 第一轮 LIMIT 截断; 第二轮今日已满 → limit_reached 拦截。"""
        _enable(daily_limit=2)
        _set_cursor_past()
        for i in range(3):
            _insert_hotspot(f"h{i}", quality_score=90 + i)
        r1 = run_auto_intake()
        assert r1["evaluated"] == 2
        assert r1["intaken"] == 2
        assert r1["limit_reached"] is False
        assert knowledge_repo.count_items() == 2
        # 第二轮: 今日已入管 2 >= limit → 直接拦截 (计数=实时 COUNT, 重启安全)
        r2 = run_auto_intake()
        assert r2["limit_reached"] is True
        assert r2["intaken"] == 0
        assert knowledge_repo.count_items() == 2

    def test_domain_hit_filter(self, temp_db):
        """域命中过滤: 命中关注域入管; 未命中跳过 (不入管)。"""
        _enable()
        SettingsService().set("interest.practice_domains", ["vuln_research"])
        _set_cursor_past()
        _insert_hotspot("hhit", title="CVE-2025-9999 漏洞复现分析")
        _insert_hotspot("hmiss", title="季度财报增长点评", tags='["合规"]', category="finance")
        result = run_auto_intake()
        assert result["intaken"] == 1
        assert result["skipped_domain"] == 1
        assert knowledge_repo.get_item(item_id_from_url("https://example.com/hhit")) is not None
        assert knowledge_repo.get_item(item_id_from_url("https://example.com/hmiss")) is None

    def test_domain_filter_disabled_passes_all(self, temp_db):
        """require_domain_hit=False → 不做域过滤, 全部候选入管。"""
        _enable(require_domain_hit=False)
        _set_cursor_past()
        _insert_hotspot("ha", title="完全无关的标题")
        _insert_hotspot("hb", title="另一个无关标题")
        result = run_auto_intake()
        assert result["intaken"] == 2
        assert result["skipped_domain"] == 0

    def test_domain_required_but_profile_empty_passes(self, temp_db):
        """require_domain_hit=True + 未配置关注域 → 不过滤 (interest 系统
        "空画像 = 无偏好"一贯语义, 先例 hotspots 加权 / M_i)。"""
        _enable()  # require_domain_hit 默认 True
        _set_cursor_past()
        _insert_hotspot("he", title="任意标题")
        result = run_auto_intake()
        assert result["intaken"] == 1
        assert result["skipped_domain"] == 0

    def test_cursor_prevents_rescan(self, temp_db):
        """游标推进到本轮 max(ingested_at) → 同批候选不重扫 (含跳过条目)。"""
        _enable(require_domain_hit=False)
        _set_cursor_past()
        _insert_hotspot("hc1", title="普通标题甲")
        _insert_hotspot("hc2", title="普通标题乙")
        r1 = run_auto_intake()
        assert r1["intaken"] == 2
        # 追加一条同分新条目后再跑: 旧两条已被游标越过
        _insert_hotspot("hc3", title="新到条目")
        r2 = run_auto_intake()
        assert r2["evaluated"] == 1
        assert r2["intaken"] == 1
        assert knowledge_repo.count_items() == 3

    def test_first_run_no_backfill(self, temp_db):
        """首跑 (无游标) = 游标落到当前时刻 → 不回填历史 (design §6 非目标)。"""
        _enable(require_domain_hit=False)
        old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        _insert_hotspot("hold", ingested_at=old)
        result = run_auto_intake()
        assert result["evaluated"] == 0
        assert result["intaken"] == 0
        assert knowledge_repo.count_items() == 0
        # 游标已落盘, 下一轮从部署时刻起算
        assert SettingsRepository().get(CURSOR_KEY)


# ---------------------------------------------------------------------------
# collect_all_job 尾部挂载 (Task 2): 日志一行 + 异常隔离不阻塞采集
# ---------------------------------------------------------------------------
class TestCollectJobMount:
    @pytest.mark.asyncio
    async def test_tick_logs_one_line(self, temp_db, monkeypatch):
        """挂载点输出规定格式日志: auto_intake: evaluated=.. intaken=.. .."""
        import backend.scheduler.jobs.collect as collect_mod
        from backend.services import auto_intake_service

        lines: list[str] = []

        class _StubLogger:
            def info(self, msg: str, *args, **kwargs) -> None:
                lines.append(msg)

            def error(self, msg: str, *args, **kwargs) -> None:
                lines.append(msg)

        monkeypatch.setattr(collect_mod, "_logger", _StubLogger())
        monkeypatch.setattr(
            auto_intake_service,
            "run_auto_intake",
            lambda: {"evaluated": 3, "intaken": 2, "skipped_domain": 1, "limit_reached": False},
        )
        await collect_mod._auto_intake_tick()
        assert lines == [
            "auto_intake: evaluated=3 intaken=2 skipped=1 limit_reached=False"
        ]

    @pytest.mark.asyncio
    async def test_tick_swallows_crash(self, temp_db, monkeypatch):
        """run_auto_intake 抛错也不阻塞采集主流程 (双层异常隔离)。"""
        import backend.scheduler.jobs.collect as collect_mod
        from backend.services import auto_intake_service

        def _boom():
            raise RuntimeError("boom")

        class _StubLogger:
            def info(self, msg: str, *args, **kwargs) -> None:
                pass

            def error(self, msg: str, *args, **kwargs) -> None:
                pass

        monkeypatch.setattr(collect_mod, "_logger", _StubLogger())
        monkeypatch.setattr(auto_intake_service, "run_auto_intake", _boom)
        await collect_mod._auto_intake_tick()  # 不抛即通过


# ---------------------------------------------------------------------------
# promote 扩展 (keyword-only, 收藏调用零变化)
# ---------------------------------------------------------------------------
class TestPromoteExtended:
    def test_extended_fields_written(self, temp_db):
        """扩展调用: source 通道 + content 正文 + category frontmatter 落 md。"""
        from backend.services.knowledge_sync import ITEMS_DIR

        item_id = sag_service.promote_favorite_to_knowledge(
            "Ext Title",
            "https://example.com/ext-1",
            content="正文内容段落",
            category="security",
            source="secnews_auto",
        )
        item = knowledge_repo.get_item(item_id)
        assert item is not None
        assert item.source == "secnews_auto"
        assert item.lifecycle == "kl:raw"
        md = (ITEMS_DIR / f"{item_id}.md").read_text(encoding="utf-8")
        assert "正文内容段落" in md
        assert 'category: "security"' in md

    def test_default_call_unchanged(self, temp_db):
        """收藏默认调用: source='secnews', 无 content/category 字段落 md。"""
        from backend.services.knowledge_sync import ITEMS_DIR

        item_id = sag_service.promote_favorite_to_knowledge(
            "Fav", "https://example.com/fav-x"
        )
        item = knowledge_repo.get_item(item_id)
        assert item.source == "secnews"
        md = (ITEMS_DIR / f"{item_id}.md").read_text(encoding="utf-8")
        assert "category:" not in md
