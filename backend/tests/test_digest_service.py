"""v1.7 Phase 4 — DigestService 测试.

覆盖:
- DigestRepository: add/get/list_by_period/list_recent/get_latest/delete/count
- create_digest: 兼容 Phase 3 (委托给 DigestRepository)
- generate_daily_digest: 昨日 Top N 简报生成 (验收 4)
- 验收 4: 每日简报生成 (函数被调用时正确产出昨日简报)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.config import config
from backend.repository import db
from backend.repository.db import get_connection
from backend.repository.digest_repo import DigestRepository, digest_repo
from backend.services.digest_service import (
    create_digest,
    generate_daily_digest,
)

_SHANGHAI_TZ = timezone(timedelta(hours=8))
_UTC = timezone.utc


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_digest.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


# ---------------------------------------------------------------------------
# 辅助: 插入 hotspots (用于 generate_daily_digest 测试)
# ---------------------------------------------------------------------------
def _insert_hotspot(
    hid: str,
    title: str,
    score: int,
    ingested_at: datetime,
    category: str = "ai",
) -> None:
    """向 hotspots 表插入一行."""
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO hotspots (
            id, title, summary, source, url, category,
            published_at, score, fetched_at, is_fallback,
            quality_score, quality_flags, ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            hid, title, "", "test-src", f"https://example.com/{hid}", category,
            ingested_at.isoformat(), score, ingested_at.isoformat(), 0,
            100, "[]", ingested_at.isoformat(),
        ),
    )


def _yesterday_shanghai_hours_ago(h: int) -> datetime:
    """返回昨日 Shanghai 时间 h 小时前的 UTC datetime (确保在昨日窗口内)."""
    now_shanghai = datetime.now(_SHANGHAI_TZ)
    yesterday_noon_shanghai = (now_shanghai - timedelta(days=1)).replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    return (yesterday_noon_shanghai - timedelta(hours=h)).astimezone(_UTC)


# ===========================================================================
# DigestRepository
# ===========================================================================
class TestDigestRepository:
    def test_add_and_get(self, temp_db):
        repo = DigestRepository()
        record = repo.add(
            "d1", "daily", "今日简报", item_ids=["h1", "h2"]
        )
        assert record["id"] == "d1"
        assert record["period"] == "daily"
        assert record["summary"] == "今日简报"
        assert record["item_ids"] == ["h1", "h2"]
        assert "created_at" in record

        fetched = repo.get("d1")
        assert fetched is not None
        assert fetched["summary"] == "今日简报"
        assert fetched["item_ids"] == ["h1", "h2"]

    def test_get_missing_returns_none(self, temp_db):
        assert DigestRepository().get("nonexistent") is None

    def test_add_upsert(self, temp_db):
        repo = DigestRepository()
        repo.add("d1", "daily", "旧摘要")
        repo.add("d1", "daily", "新摘要", item_ids=["x"])
        record = repo.get("d1")
        assert record["summary"] == "新摘要"
        assert record["item_ids"] == ["x"]

    def test_add_default_item_ids(self, temp_db):
        repo = DigestRepository()
        record = repo.add("d1", "daily", "无 item_ids")
        assert record["item_ids"] == []

    def test_list_by_period(self, temp_db):
        repo = DigestRepository()
        repo.add("d1", "daily", "简报1")
        repo.add("w1", "weekly", "周报1")
        repo.add("d2", "daily", "简报2")

        daily = repo.list_by_period(period="daily")
        assert len(daily) == 2
        assert all(r["period"] == "daily" for r in daily)

        weekly = repo.list_by_period(period="weekly")
        assert len(weekly) == 1
        assert weekly[0]["id"] == "w1"

    def test_list_recent(self, temp_db):
        repo = DigestRepository()
        repo.add("d1", "daily", "简报1")
        repo.add("d2", "daily", "简报2")
        repo.add("w1", "weekly", "周报1")

        recent = repo.list_recent(limit=10)
        assert len(recent) == 3
        # 按 created_at DESC, 最后插入的在前
        assert recent[0]["id"] == "w1"

    def test_list_recent_limit(self, temp_db):
        repo = DigestRepository()
        for i in range(5):
            repo.add(f"d{i}", "daily", f"简报{i}")
        recent = repo.list_recent(limit=2)
        assert len(recent) == 2

    def test_get_latest(self, temp_db):
        repo = DigestRepository()
        repo.add("d1", "daily", "简报1")
        repo.add("d2", "daily", "简报2")
        latest = repo.get_latest()
        assert latest is not None
        assert latest["id"] == "d2"

    def test_get_latest_by_period(self, temp_db):
        repo = DigestRepository()
        repo.add("d1", "daily", "简报1")
        repo.add("w1", "weekly", "周报1")
        repo.add("d2", "daily", "简报2")
        latest_daily = repo.get_latest(period="daily")
        assert latest_daily is not None
        assert latest_daily["id"] == "d2"

    def test_get_latest_empty_returns_none(self, temp_db):
        assert DigestRepository().get_latest() is None

    def test_delete(self, temp_db):
        repo = DigestRepository()
        repo.add("d1", "daily", "简报1")
        assert repo.delete("d1") is True
        assert repo.get("d1") is None
        assert repo.delete("d1") is False  # 再删返回 False

    def test_count(self, temp_db):
        repo = DigestRepository()
        repo.add("d1", "daily", "简报1")
        repo.add("d2", "daily", "简报2")
        repo.add("w1", "weekly", "周报1")
        assert repo.count() == 3
        assert repo.count(period="daily") == 2
        assert repo.count(period="weekly") == 1

    def test_malformed_item_ids_returns_empty_list(self, temp_db):
        """item_ids 列损坏时, get() 返回空列表而非崩溃."""
        conn = get_connection()
        conn.execute(
            "INSERT INTO digests (id, period, summary, item_ids, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("bad1", "daily", "损坏", "not-json", datetime.now(_UTC).isoformat()),
        )
        record = DigestRepository().get("bad1")
        assert record is not None
        assert record["item_ids"] == []


# ===========================================================================
# create_digest (Phase 3 兼容)
# ===========================================================================
class TestCreateDigestCompat:
    def test_returns_record_with_parsed_item_ids(self, temp_db):
        result = create_digest("d1", period="daily", summary="测试", item_ids=["h1", "h2"])
        assert result["id"] == "d1"
        assert result["period"] == "daily"
        assert result["summary"] == "测试"
        assert result["item_ids"] == ["h1", "h2"]

    def test_default_args(self, temp_db):
        result = create_digest("d2")
        assert result["period"] == "daily"
        assert result["summary"] == ""
        assert result["item_ids"] == []

    def test_upsert(self, temp_db):
        create_digest("d1", summary="旧")
        create_digest("d1", summary="新")
        record = DigestRepository().get("d1")
        assert record["summary"] == "新"


# ===========================================================================
# generate_daily_digest (Phase 4)
# ===========================================================================
class TestGenerateDailyDigest:
    def test_empty_db_returns_digest_with_zero_count(self, temp_db):
        """无任何 hotspots 时, 仍生成简报 (count=0)."""
        result = generate_daily_digest()
        assert result["id"].startswith("digest-")
        assert result["period"] == "daily"
        assert result["count"] == 0
        assert result["item_ids"] == []
        assert "昨日共 0 篇" in result["summary"]

    def test_generates_digest_with_top_n(self, temp_db):
        """昨日有 5 篇文章, 默认取 Top 3."""
        # 昨日 5 篇, 分数不同
        _insert_hotspot("h1", "AI 突破", score=80, ingested_at=_yesterday_shanghai_hours_ago(1))
        _insert_hotspot("h2", "安全事件", score=95, ingested_at=_yesterday_shanghai_hours_ago(2))
        _insert_hotspot("h3", "金融动态", score=70, ingested_at=_yesterday_shanghai_hours_ago(3))
        _insert_hotspot("h4", "创业新闻", score=60, ingested_at=_yesterday_shanghai_hours_ago(4))
        _insert_hotspot("h5", "招标信息", score=85, ingested_at=_yesterday_shanghai_hours_ago(5))

        result = generate_daily_digest()
        assert result["count"] == 5
        # Top 3 by score: h2(95), h5(85), h1(80)
        assert result["item_ids"] == ["h2", "h5", "h1"]
        assert "昨日共 5 篇" in result["summary"]
        assert "Top 3" in result["summary"]
        # 摘要包含最高分文章标题
        assert "安全事件" in result["summary"]

    def test_top_n_custom(self, temp_db):
        """top_n=2 时只取 Top 2."""
        _insert_hotspot("h1", "标题1", score=50, ingested_at=_yesterday_shanghai_hours_ago(1))
        _insert_hotspot("h2", "标题2", score=90, ingested_at=_yesterday_shanghai_hours_ago(2))
        _insert_hotspot("h3", "标题3", score=70, ingested_at=_yesterday_shanghai_hours_ago(3))

        result = generate_daily_digest(top_n=2)
        assert result["count"] == 3
        assert len(result["item_ids"]) == 2
        assert result["item_ids"] == ["h2", "h3"]

    def test_excludes_today_articles(self, temp_db):
        """今日文章不计入昨日简报."""
        # 昨日 1 篇
        _insert_hotspot("y1", "昨日文章", score=80, ingested_at=_yesterday_shanghai_hours_ago(1))
        # 今日 1 篇 (在今日 00:00 Shanghai 之后)
        now_utc = datetime.now(_UTC)
        _insert_hotspot("t1", "今日文章", score=100, ingested_at=now_utc)

        result = generate_daily_digest()
        assert result["count"] == 1
        assert result["item_ids"] == ["y1"]

    def test_excludes_articles_outside_window(self, temp_db):
        """前日及更早的文章不计入昨日简报."""
        # 前天 12:00 Shanghai (在昨日窗口外)
        now_shanghai = datetime.now(_SHANGHAI_TZ)
        day_before_yesterday = (now_shanghai - timedelta(days=2)).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        _insert_hotspot(
            "old1", "前日文章", score=100,
            ingested_at=day_before_yesterday.astimezone(_UTC),
        )
        # 昨日 1 篇
        _insert_hotspot("y1", "昨日文章", score=50, ingested_at=_yesterday_shanghai_hours_ago(1))

        result = generate_daily_digest()
        assert result["count"] == 1
        assert result["item_ids"] == ["y1"]

    def test_id_format_is_digest_yyyymmdd(self, temp_db):
        """简报 ID 格式为 digest-YYYY-MM-DD (昨日 Shanghai 日期)."""
        result = generate_daily_digest()
        now_shanghai = datetime.now(_SHANGHAI_TZ)
        yesterday_shanghai = now_shanghai - timedelta(days=1)
        expected_id = f"digest-{yesterday_shanghai.strftime('%Y-%m-%d')}"
        assert result["id"] == expected_id

    def test_upsert_same_day(self, temp_db):
        """同日多次生成, 后者覆盖前者."""
        _insert_hotspot("h1", "文章1", score=80, ingested_at=_yesterday_shanghai_hours_ago(1))
        first = generate_daily_digest()
        assert first["count"] == 1

        # 再加一篇, 重新生成
        _insert_hotspot("h2", "文章2", score=90, ingested_at=_yesterday_shanghai_hours_ago(2))
        second = generate_daily_digest()
        assert second["count"] == 2
        assert second["id"] == first["id"]  # 同 ID (覆盖)

        # 数据库只有 1 条
        all_digests = DigestRepository().list_recent()
        assert len(all_digests) == 1

    def test_record_persisted_to_db(self, temp_db):
        """generate_daily_digest 写入的记录可通过 DigestRepository.get 读出."""
        _insert_hotspot("h1", "AI 突破", score=80, ingested_at=_yesterday_shanghai_hours_ago(1))
        result = generate_daily_digest()
        fetched = DigestRepository().get(result["id"])
        assert fetched is not None
        assert fetched["summary"] == result["summary"]
        assert fetched["item_ids"] == result["item_ids"]

    def test_injected_repo(self, temp_db):
        """可注入自定义 DigestRepository (测试用)."""
        _insert_hotspot("h1", "文章1", score=80, ingested_at=_yesterday_shanghai_hours_ago(1))
        custom_repo = DigestRepository()
        result = generate_daily_digest(repo=custom_repo)
        assert result["id"].startswith("digest-")
        # 通过注入的 repo 也能读到
        assert custom_repo.get(result["id"]) is not None


# ===========================================================================
# 验收 4: 每日 08:00 生成简报
# ===========================================================================
class TestAcceptance4DailyDigest:
    def test_digest_generated_with_correct_summary(self, temp_db):
        """验收 4: generate_daily_digest 被调用时, 产出包含昨日 Top 文章的简报."""
        _insert_hotspot("h1", "重磅：AI 新模型发布", score=95,
                        ingested_at=_yesterday_shanghai_hours_ago(1))
        _insert_hotspot("h2", "重大安全漏洞披露", score=88,
                        ingested_at=_yesterday_shanghai_hours_ago(2))
        _insert_hotspot("h3", "股市震荡", score=70,
                        ingested_at=_yesterday_shanghai_hours_ago(3))

        result = generate_daily_digest()

        # 简报存在且包含关键字段
        assert result["id"].startswith("digest-")
        assert result["period"] == "daily"
        assert "昨日共 3 篇" in result["summary"]
        assert "重磅：AI 新模型发布" in result["summary"]
        # Top 文章 ID 在 item_ids 中
        assert "h1" in result["item_ids"]
        # 最高分排第一
        assert result["item_ids"][0] == "h1"

    def test_digest_id_changes_per_day(self, temp_db):
        """不同日期生成的简报 ID 不同 (由日期决定)."""
        # 同一天内多次生成, ID 相同 (覆盖)
        r1 = generate_daily_digest()
        r2 = generate_daily_digest()
        assert r1["id"] == r2["id"]

    def test_digest_can_be_fetched_after_generation(self, temp_db):
        """验收 4 (集成): 简报生成后, 可通过 repository 读取供前端展示."""
        _insert_hotspot("h1", "测试文章", score=50,
                        ingested_at=_yesterday_shanghai_hours_ago(1))
        result = generate_daily_digest()

        # 模拟前端通过 list_recent 获取最新简报
        recent = DigestRepository().list_recent(limit=1)
        assert len(recent) == 1
        assert recent[0]["id"] == result["id"]
        assert recent[0]["summary"] == result["summary"]
