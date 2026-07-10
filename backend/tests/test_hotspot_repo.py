"""HotspotRepository 单元测试

每个测试使用 tmp_path 隔离的临时 SQLite，并通过 monkeypatch
重定向 ``config.db_path``，避免污染真实 ``backend/hotspot.db``。

时间窗口注意事项：``query()`` 的 SQL 过滤使用
``datetime('now', '-X hours')`` 作为下界，所以测试插入的
``published_at`` 必须是 D7 / 24h 窗口内的时间点。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.config import config
from backend.domain.enums import Category, TimeRange
from backend.domain.models import HotspotItem
from backend.repository import db
from backend.repository.hotspot_repo import HotspotRepository


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(config, "db_path", test_db)
    # Phase 9.2: 关闭任何已缓存的连接（之前测试可能缓存了真实 DB 的连接）
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def repo(temp_db) -> HotspotRepository:
    return HotspotRepository()


def _make_item(
    id_: str,
    category: Category = Category.AI,
    title: str = "Title",
    *,
    published_at: datetime | None = None,
    is_fallback: bool = False,
    source: str = "unit-test",
    quality_flags: list[str] | None = None,
    bid_status: str | None = None,
) -> HotspotItem:
    """构造一个 tz-aware 时间戳的 HotspotItem；默认时间 = now - 1h。"""
    if published_at is None:
        published_at = datetime.now(timezone.utc) - timedelta(hours=1)
    return HotspotItem(
        id=id_,
        title=title,
        source=source,
        url=f"https://example.com/{id_}",
        category=category,
        published_at=published_at,
        fetched_at=published_at,
        is_fallback=is_fallback,
        quality_flags=quality_flags or [],
        bid_status=bid_status,
    )


# ---------------------------------------------------------------------------
# upsert
# ---------------------------------------------------------------------------
def test_upsert_insert_new(repo):
    items = [_make_item(f"a-{i}") for i in range(3)]
    affected = repo.upsert_many(items)
    assert affected == 3
    counts = repo.count_by_category()
    assert counts["ai"] == 3


def test_upsert_update_existing(repo):
    """同 id 第二次 upsert 应更新字段。"""
    first = _make_item("dup-1", title="original")
    repo.upsert_many([first])
    second = _make_item("dup-1", title="updated")
    repo.upsert_many([second])

    got = repo.get_by_id("dup-1")
    assert got is not None
    assert got.title == "updated"
    # 总行数仍为 1（不是 2）
    counts = repo.count_by_category()
    assert counts["ai"] == 1


# ---------------------------------------------------------------------------
# query — 分类 / 时间 / 关键词
# ---------------------------------------------------------------------------
def test_query_basic(repo):
    """5 条 ai 全部能 query 出来。"""
    repo.upsert_many([_make_item(f"a-{i}", Category.AI) for i in range(5)])
    items, cursor = repo.query(Category.AI, time_range=TimeRange.D7, limit=10)
    assert len(items) == 5
    assert cursor is None
    for it in items:
        assert it.category is Category.AI


def test_query_by_time_range(repo):
    """time_range=D7 过滤 7 天窗口内的数据。"""
    now = datetime.now(timezone.utc)
    in_window = now - timedelta(hours=1)
    out_of_window = now - timedelta(days=10)
    repo.upsert_many(
        [
            _make_item("recent-1", published_at=in_window),
            _make_item("recent-2", published_at=in_window - timedelta(hours=1)),
            _make_item("old-1", published_at=out_of_window),
        ]
    )
    items, _ = repo.query(Category.AI, time_range=TimeRange.D7, limit=10)
    ids = {it.id for it in items}
    # D7 (168h) 应只包含 1h 和 2h 前那两条
    assert "recent-1" in ids
    assert "recent-2" in ids
    assert "old-1" not in ids


# ---------------------------------------------------------------------------
# Phase 42: count_unique_urls_in_range — 用于 list 分页 total
# ---------------------------------------------------------------------------
def test_count_unique_urls_vs_count_in_range(repo):
    """同 url 多次入库: count_in_range 按行数, count_unique_urls_in_range 按 url。

    实际场景: security 采集器入库 841 行 (重复 url 200+), 列表去重后只 83 条 unique。
    total 字段之前用 count_in_range → 841, 改用 count_unique_urls_in_range → 实际 unique 数。
    """
    # 1 个 url 在 ai/security/finance 各 1 行 → 3 行
    # 2 个独立 url 在 bid 各 1 行 → 2 行
    # 共 5 行, 但 unique url = 3
    now = datetime.now(timezone.utc) - timedelta(hours=1)
    items = [
        _make_item("dup-a-ai", category=Category.AI, source="x",
                   published_at=now),
        _make_item("dup-a-sec", category=Category.SECURITY, source="y",
                   published_at=now),
        _make_item("dup-a-fin", category=Category.FINANCE, source="z",
                   published_at=now),
        _make_item("bid-only-1", category=Category.BID, source="w",
                   published_at=now),
        _make_item("bid-only-2", category=Category.BID, source="w",
                   published_at=now),
    ]
    # 改 url 让前 3 条相同
    items[0].__dict__["url"] = "https://shared.example.com/a"
    items[1].__dict__["url"] = "https://shared.example.com/a"
    items[2].__dict__["url"] = "https://shared.example.com/a"
    repo.upsert_many(items)

    # 注意: 5 条都 different id, 所以 count_in_range = 5
    n_rows = repo.count_in_range(TimeRange.D7, category="all")
    assert n_rows == 5

    # unique url = 3 (https://shared.example.com/a + 2 个 bid)
    n_unique = repo.count_unique_urls_in_range(TimeRange.D7, category="all")
    assert n_unique == 3

    # 按分类
    n_unique_ai = repo.count_unique_urls_in_range(TimeRange.D7, category="ai")
    assert n_unique_ai == 1
    n_unique_bid = repo.count_unique_urls_in_range(TimeRange.D7, category="bid")
    assert n_unique_bid == 2


def test_count_unique_urls_excludes_historical_bid(repo):
    """historical_bid 标记的行不计入 unique (与 query 口径一致)。"""
    from datetime import timezone, timedelta
    now = datetime.now(timezone.utc) - timedelta(hours=1)
    items = [
        _make_item("real-1", category=Category.BID, source="x",
                   published_at=now, quality_flags=[]),
        _make_item("hist-1", category=Category.BID, source="x",
                   published_at=now, quality_flags=["historical_bid"]),
    ]
    repo.upsert_many(items)
    assert repo.count_in_range(TimeRange.D7, category="bid") == 1
    assert repo.count_unique_urls_in_range(TimeRange.D7, category="bid") == 1


def test_query_by_keyword_fts(repo):
    """query() 的 keyword 过滤应走 FTS5 并匹配 title 关键词。

    FTS5 的 unicode61 tokeniser 把英文空白分词，因此用整个
    大小写一致的词作为关键词最稳。这里用 ``OpenAI`` 搜索，
    预期只命中标题中含 ``OpenAI`` 整词的那条记录。
    """
    repo.upsert_many(
        [
            _make_item("k-1", title="OpenAI launches new GPT model"),
            _make_item("k-2", title="Stock market news today"),
            _make_item("k-3", title="Open source AI framework"),
        ]
    )
    items, _ = repo.query(
        None, time_range=TimeRange.D7, keyword="OpenAI", limit=10
    )
    ids = {it.id for it in items}
    # FTS5 命中 'OpenAI' 整词的只有 k-1
    assert ids == {"k-1"}

    # 另一个关键词 'news' 命中 k-2
    items, _ = repo.query(
        None, time_range=TimeRange.D7, keyword="news", limit=10
    )
    ids = {it.id for it in items}
    assert ids == {"k-2"}


# ---------------------------------------------------------------------------
# query — 游标分页
# ---------------------------------------------------------------------------
def test_query_cursor_pagination(repo):
    """10 条数据，limit=3，多次翻页无重复且能取完。"""
    now = datetime.now(timezone.utc)
    items = [
        _make_item(f"p-{i:02d}", published_at=now - timedelta(hours=i))
        for i in range(10)
    ]
    repo.upsert_many(items)

    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        page, cursor = repo.query(
            Category.AI, time_range=TimeRange.D7, limit=3, cursor=cursor
        )
        seen.extend(it.id for it in page)
        pages += 1
        if cursor is None:
            break
        # 安全阀：最多 10 页
        assert pages < 10

    # 10 条全部取到、且不重复
    assert len(seen) == 10
    assert len(set(seen)) == 10
    assert set(seen) == {f"p-{i:02d}" for i in range(10)}


def test_query_next_cursor_format(repo):
    """next_cursor 形如 ``<unix_ts>_<id>``。"""
    now = datetime.now(timezone.utc)
    repo.upsert_many(
        [
            _make_item("c-1", published_at=now - timedelta(hours=1)),
            _make_item("c-2", published_at=now - timedelta(hours=2)),
            _make_item("c-3", published_at=now - timedelta(hours=3)),
        ]
    )
    items, cursor = repo.query(Category.AI, limit=1)
    assert len(items) == 1
    assert cursor is not None
    # 形如 '<unix>_<id>'
    parts = cursor.split("_", 1)
    assert len(parts) == 2
    assert parts[1] == items[-1].id
    # unix 部分是数字
    int(parts[0])  # raises if not int


# ---------------------------------------------------------------------------
# search / get_by_id / count_by_category
# ---------------------------------------------------------------------------
def test_search_returns_match(repo):
    """search() 走 FTS5，按 title/summary 匹配。"""
    repo.upsert_many(
        [
            _make_item("s-1", title="ABC corp announces merger"),
            _make_item("s-2", title="DEF corp launches product"),
            _make_item("s-3", title="GHI corp stock rises"),
        ]
    )
    items = repo.search("ABC", limit=3)
    assert len(items) == 1
    assert items[0].id == "s-1"


def test_get_by_id_found_and_not_found(repo):
    repo.upsert_many([_make_item("g-1", title="exists")])
    got = repo.get_by_id("g-1")
    assert got is not None
    assert got.title == "exists"

    missing = repo.get_by_id("nope")
    assert missing is None


def test_count_by_category(repo):
    """5ai + 3sec + 2tech → count 返回 ai=7 (tech 合并), sec=3, 其它类 0。

    Phase 35: ``tech`` 在 SQL 层合并到 ``ai``, 输出 dict 不再包含
    ``tech`` key, 与 UI「科技/AI」合并展示对齐。
    """
    repo.upsert_many(
        [_make_item(f"ai-{i}", Category.AI) for i in range(5)]
        + [_make_item(f"sec-{i}", Category.SECURITY) for i in range(3)]
        + [_make_item(f"tech-{i}", Category.TECH) for i in range(2)]
    )
    counts = repo.count_by_category()
    assert counts == {
        "ai": 7,  # 5 ai + 2 tech
        "security": 3,
        "finance": 0,
        "startup": 0,
        "bid": 0,
        "github": 0,
    }


# ---------------------------------------------------------------------------
# cleanup_older_than
# ---------------------------------------------------------------------------
def test_cleanup_older_than(repo):
    """cleanup_older_than(30) 应删除 published_at 早于 30 天的数据。"""
    now = datetime.now(timezone.utc)
    repo.upsert_many(
        [
            _make_item("cl-old-1", published_at=now - timedelta(days=60)),
            _make_item("cl-old-2", published_at=now - timedelta(days=45)),
            _make_item("cl-new", published_at=now - timedelta(days=5)),
        ]
    )
    deleted = repo.cleanup_older_than(30)
    assert deleted == 2

    items, _ = repo.query(None, time_range=TimeRange.D30, limit=50)
    remaining = {it.id for it in items}
    # Only 'cl-new' 还在
    assert "cl-new" in remaining
    assert "cl-old-1" not in remaining
    assert "cl-old-2" not in remaining


# ---------------------------------------------------------------------------
# Phase 21: historical_bid 过滤 + bid_status 字段 (Phase 20+)
# ---------------------------------------------------------------------------
def test_query_excludes_historical_bid(repo):
    """quality_flags 含 historical_bid 的标讯不应出现在 query 结果中。

    原因: bid_recency_gate 已识别为历史标讯(标题含历史年份/published_at
    超过 180d),即使 loose 模式仍入库,query 时也不应展示给用户。
    """
    now = datetime.now(timezone.utc)
    repo.upsert_many(
        [
            # 标讯 A: 正常招标中 → 应出现
            _make_item(
                "bid-normal",
                category=Category.BID,
                title="X 项目等保 2.0 采购公告",
                source="test",
                quality_flags=[],
                bid_status="招标中",
            ),
            # 标讯 B: historical_bid flag → 不应出现
            _make_item(
                "bid-historical",
                category=Category.BID,
                title="X 项目 2022-2023 年设备采购",
                source="test",
                quality_flags=["historical_bid"],
                bid_status="其他",
            ),
            # 标讯 C: historical_bid flag + 其他 flag 混在一起 → 不应出现
            _make_item(
                "bid-historical-mixed",
                category=Category.BID,
                title="X 项目 2021 年服务采购",
                source="test",
                quality_flags=["author_unknown", "historical_bid", "url_duplicate"],
                bid_status="其他",
            ),
        ]
    )
    items, _ = repo.query(Category.BID, time_range=TimeRange.D7, limit=10)
    ids = {it.id for it in items}
    assert "bid-normal" in ids
    assert "bid-historical" not in ids, "historical_bid flag 应该过滤掉"
    assert "bid-historical-mixed" not in ids, "含 historical_bid 的混合 flag 也应过滤掉"


def test_query_returns_bid_status(repo):
    """query 应返回 bid_status 字段(Phase 20+)。"""
    repo.upsert_many(
        [
            _make_item(
                "bid-status-1",
                category=Category.BID,
                title="X 项目中标候选人公示",
                source="test",
                quality_flags=[],
                bid_status="中标",
            ),
        ]
    )
    items, _ = repo.query(Category.BID, time_range=TimeRange.D7, limit=10)
    assert len(items) == 1
    assert items[0].bid_status == "中标"


def test_search_excludes_historical_bid(repo):
    """search() 走 FTS5 路径,同样应排除 historical_bid。

    注: FTS5 unicode61 tokenizer 对中文按字分词,phrase 查询需要带
    引号匹配具体字面量。这里用英文短串验证过滤器逻辑。
    """
    repo.upsert_many(
        [
            _make_item(
                "s-normal",
                category=Category.BID,
                title="WAF procurement announcement for X project",
                source="test",
                quality_flags=[],
                bid_status="招标中",
            ),
            _make_item(
                "s-historical",
                category=Category.BID,
                title="WAF 2022 historical procurement announcement",
                source="test",
                quality_flags=["historical_bid"],
                bid_status="其他",
            ),
        ]
    )
    results = repo.search("WAF procurement", limit=10)
    ids = {it.id for it in results}
    assert "s-normal" in ids, "正常标讯应被搜索到"
    assert "s-historical" not in ids, "search 路径也应过滤 historical_bid"
