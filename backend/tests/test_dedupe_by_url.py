"""HotspotService._dedupe_by_url 测试（Phase 9 + Phase 45 修复）。

覆盖（Phase 45 修复后）:
- 同 url 重复 item 时只保留 winner
- 优先级：url_check_status=verified > not_fallback > quality_score > fetched_at > id
- 完全同分时保留首次出现的 winner
- 用户截图场景（Phase 45 关键 bug 修复）

Phase 45 关键修复:
- 移除 ``title_len`` 排序 key — 长 title 不等于真 title
  (曾导致同 URL 重复入库时错把 list 页抓到的长 title 摘要当 winner)
- ``url_check_status=verified`` 最优先 (详情页 ``<title>`` 验过)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import HttpUrl

from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.services.hotspot_service import HotspotService


def _make(
    id_: str,
    title: str,
    url: str,
    *,
    quality_score: int = 80,
    is_fallback: bool = False,
    fetched_at: datetime | None = None,
    url_check_status: Optional[str] = None,
) -> HotspotItem:
    ts = fetched_at or datetime(2026, 1, 1, tzinfo=timezone.utc)
    return HotspotItem(
        id=id_,
        title=title,
        summary="",
        source="36氪AI",
        url=HttpUrl(url),
        category=Category.AI,
        published_at=ts,
        fetched_at=ts,
        quality_score=quality_score,
        is_fallback=is_fallback,
        url_check_status=url_check_status,
    )


def test_dedupe_empty():
    assert HotspotService._dedupe_by_url([]) == []


def test_dedupe_single_item():
    items = [_make("a", "title", "https://x.com/1")]
    out = HotspotService._dedupe_by_url(items)
    assert len(out) == 1
    assert out[0].id == "a"


def test_dedupe_different_urls_kept_all():
    items = [
        _make("a", "title-a", "https://x.com/1"),
        _make("b", "title-b", "https://x.com/2"),
        _make("c", "title-c", "https://x.com/3"),
    ]
    out = HotspotService._dedupe_by_url(items)
    assert len(out) == 3


def test_dedupe_prefers_higher_quality():
    url = "https://x.com/article-1"
    items = [
        _make("a", "title", url, quality_score=70),
        _make("b", "title", url, quality_score=80),
    ]
    out = HotspotService._dedupe_by_url(items)
    assert len(out) == 1
    assert out[0].id == "b"  # b quality 80 > 70,严格更优,胜出


def test_dedupe_prefers_non_fallback():
    url = "https://x.com/article-2"
    items = [
        _make("a", "title", url, quality_score=80, is_fallback=True),
        _make("b", "title", url, quality_score=80, is_fallback=False),
    ]
    out = HotspotService._dedupe_by_url(items)
    assert len(out) == 1
    assert out[0].id == "b"  # b not_fallback,严格更优


def test_dedupe_prefers_newer_fetched_at():
    url = "https://x.com/article-4"
    t_old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t_new = datetime(2026, 1, 2, tzinfo=timezone.utc)
    items = [
        _make("a", "title", url, quality_score=80, fetched_at=t_old),
        _make("b", "title", url, quality_score=80, fetched_at=t_new),
    ]
    out = HotspotService._dedupe_by_url(items)
    assert len(out) == 1
    assert out[0].id == "b"  # b fetched_at 更新


def test_dedupe_no_longer_prefers_title_len():
    """Phase 45 关键修复: title_len 长短不再是 winner 选择标准。

    同 url 不同 title 的两条 item,质量相同,长 title 不应胜出。
    """
    url = "https://x.com/article-3"
    items = [
        _make("a", "短", url, quality_score=80),
        _make("b", "这是一个很长的标题信息很丰富", url, quality_score=80),
    ]
    out = HotspotService._dedupe_by_url(items)
    assert len(out) == 1
    # Phase 45 修复: 完全同分(quality/is_fallback/fetched_at 都同) → 保留首次出现的 a
    assert out[0].id == "a"


def test_dedupe_verified_wins_over_pending():
    """Phase 45 关键测试: url_check_status=verified 最优先。

    即使长 title + 高 quality_score 的 pending item 在前,
    verified 的短 title item 也应胜出 (详情页已验过)。
    """
    url = "https://x.com/article-5"
    items = [
        # 短 title 但 verified — 胜出
        _make("a_short_verified", "正", url, quality_score=80, url_check_status="verified"),
        # 长 title 但 pending — 输
        _make("b_long_pending", "这是一个很长的标题信息很丰富", url, quality_score=80, url_check_status="pending"),
    ]
    out = HotspotService._dedupe_by_url(items)
    assert len(out) == 1
    assert out[0].id == "a_short_verified"  # verified 优先于 title_len


def test_dedupe_verified_wins_even_when_longer_pending_first():
    """即使 long title 的 pending item 先入库,verified 短 title 后到也应替换。"""
    url = "https://x.com/article-6"
    items = [
        _make("a_long_pending", "这是一个很长的标题信息很丰富", url, quality_score=80, url_check_status="pending"),
        _make("b_short_verified", "正", url, quality_score=80, url_check_status="verified"),
    ]
    out = HotspotService._dedupe_by_url(items)
    assert len(out) == 1
    assert out[0].id == "b_short_verified"


def test_dedupe_mismatch_loses_to_verified():
    """mismatch (详情页 title 验过不一致) 应输给 verified。"""
    url = "https://x.com/article-7"
    items = [
        _make("a_mismatch", "短", url, quality_score=80, url_check_status="mismatch"),
        _make("b_verified", "正", url, quality_score=80, url_check_status="verified"),
    ]
    out = HotspotService._dedupe_by_url(items)
    assert len(out) == 1
    assert out[0].id == "b_verified"


def test_dedupe_user_screenshot_scenario():
    """Phase 45 用户截图场景: 安全内参两条同 url 不同 title。

    - _10: 「美国陆军网站遭篡改，出现"辱骂特朗普"等涉政内容」(verified, 正确)
    - _20: 「目前发现多个子域名均受影响，但攻击路径尚不明确」(pending, 错误)

    期望保留 _10 (verified 优先),而非 _20 (长 title 摘要).
    """
    url = "https://www.secrss.com/articles/91989"
    items = [
        _make(
            "security_安全内参_20",
            "目前发现多个子域名均受影响，但攻击路径尚不明确，攻击者身份未知。",
            url,
            quality_score=10,
            url_check_status="pending",
        ),
        _make(
            "security_安全内参_10",
            "美国陆军网站遭篡改，出现“辱骂特朗普”等涉政内容",
            url,
            quality_score=80,
            url_check_status="verified",
        ),
    ]
    out = HotspotService._dedupe_by_url(items)
    assert len(out) == 1
    assert out[0].id == "security_安全内参_10"
    assert "美国陆军" in out[0].title
    assert "特朗普" in out[0].title


def test_dedupe_keeps_first_when_fully_tied():
    """完全同分(5 段全部相同)时保留首次出现的 winner。"""
    fixed = datetime(2026, 1, 1, tzinfo=timezone.utc)
    items = [
        _make("a", "title", "https://x.com/1", quality_score=80, fetched_at=fixed, url_check_status="verified"),
        _make("b", "title", "https://x.com/1", quality_score=80, fetched_at=fixed, url_check_status="verified"),
        _make("c", "title", "https://x.com/2", quality_score=80, fetched_at=fixed, url_check_status="verified"),
        _make("d", "title", "https://x.com/2", quality_score=80, fetched_at=fixed, url_check_status="verified"),
    ]
    out = HotspotService._dedupe_by_url(items)
    assert len(out) == 2
    # 完全同分 → 保留首次
    assert out[0].id == "a"
    assert out[1].id == "c"


def test_dedupe_three_items_same_url_picks_verified():
    """同 url 3 条 items,verified > 长 title (不再有 title_len 维度)。"""
    url = "https://x.com/three"
    items = [
        _make("a_pending_long", "这是一个很长的标题信息丰富", url, quality_score=80, url_check_status="pending"),
        _make("b_pending_short", "短", url, quality_score=80, url_check_status="pending"),
        _make("c_verified_short", "正", url, quality_score=80, url_check_status="verified"),
    ]
    out = HotspotService._dedupe_by_url(items)
    assert len(out) == 1
    assert out[0].id == "c_verified_short"  # verified 优先


def test_dedupe_id_tiebreak_lexicographic():
    """完全同分(除 id 外)时,id 字典序小者优先。"""
    url = "https://x.com/id-tie"
    fixed = datetime(2026, 1, 1, tzinfo=timezone.utc)
    items = [
        _make("zzz_loser", "title", url, quality_score=80, fetched_at=fixed, url_check_status="verified"),
        _make("aaa_winner", "title", url, quality_score=80, fetched_at=fixed, url_check_status="verified"),
    ]
    out = HotspotService._dedupe_by_url(items)
    assert len(out) == 1
    # aaa < zzz 字典序
    assert out[0].id == "aaa_winner"
