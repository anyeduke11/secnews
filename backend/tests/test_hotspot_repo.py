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


def _recent_ts(*, hours: float = 1.0) -> datetime:
    """``now - hours`` 钳制进 D7 日历周窗口。

    时间边界根治 (2026-08-31): D7 是「本周周一 00:00」日历周语义 —
    每逢周一 00:00-01:00 (本地), now-Nh 的 recent 种子会落入上周窗口,
    query/count 断言集体腐坏。钳制规则: 种子落在窗口内保持原值 (其余
    6 天 23 小时行为不变); 落在窗外取窗口起点 +1min。
    """
    ts = datetime.now(timezone.utc) - timedelta(hours=hours)
    floor = TimeRange.D7.start_datetime() + timedelta(minutes=1)
    return max(ts, floor)


def _make_item(
    id_: str,
    category: Category = Category.AI,
    title: str = "Title",
    *,
    published_at: datetime | None = None,
    is_fallback: bool = False,
    source: str = "unit-test",
    quality_flags: list[str] | None = None,
) -> HotspotItem:
    """构造一个 tz-aware 时间戳的 HotspotItem；默认时间 = now - 1h
    (经 :func:`_recent_ts` 钳制, 见其 docstring)。"""
    if published_at is None:
        published_at = _recent_ts(hours=1)
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
    in_window = _recent_ts(hours=1)
    out_of_window = now - timedelta(days=10)
    repo.upsert_many(
        [
            _make_item("recent-1", published_at=in_window),
            _make_item("recent-2", published_at=_recent_ts(hours=2)),
            _make_item("old-1", published_at=out_of_window),
        ]
    )
    items, _ = repo.query(Category.AI, time_range=TimeRange.D7, limit=10)
    ids = {it.id for it in items}
    # D7 (日历周) 应只包含两个 recent 种子 (经 _recent_ts 钳制保证在窗口内)
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
    # 1 个 url 在 ai/finance/github 各 1 行 → 3 行
    # 2 个独立 url 在 security 各 1 行 → 2 行
    # 共 5 行, 但 unique url = 3
    now = _recent_ts(hours=1)
    items = [
        _make_item("dup-a-ai", category=Category.AI, source="x",
                   published_at=now),
        _make_item("dup-a-fin", category=Category.FINANCE, source="y",
                   published_at=now),
        _make_item("dup-a-gh", category=Category.GITHUB, source="z",
                   published_at=now),
        _make_item("sec-only-1", category=Category.SECURITY, source="w",
                   published_at=now),
        _make_item("sec-only-2", category=Category.SECURITY, source="w",
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

    # unique url = 3 (https://shared.example.com/a + 2 个 security)
    n_unique = repo.count_unique_urls_in_range(TimeRange.D7, category="all")
    assert n_unique == 3

    # 按分类 (注意: ai 桶查询含 IN ('ai','tech') 合并口径, 故用 security 验证)
    n_unique_ai = repo.count_unique_urls_in_range(TimeRange.D7, category="ai")
    assert n_unique_ai == 1
    n_unique_sec = repo.count_unique_urls_in_range(TimeRange.D7, category="security")
    assert n_unique_sec == 2


def test_count_unique_urls_excludes_historical_hidden_flag(repo):
    """historical_bid 隐藏标记的行不计入 unique (与 query 口径一致; 标记名保留兼容历史数据)。"""
    now = _recent_ts(hours=1)
    items = [
        _make_item("real-1", category=Category.TECH, source="x",
                   published_at=now, quality_flags=[]),
        _make_item("hist-1", category=Category.TECH, source="x",
                   published_at=now, quality_flags=["historical_bid"]),
    ]
    repo.upsert_many(items)
    assert repo.count_in_range(TimeRange.D7, category="tech") == 1
    assert repo.count_unique_urls_in_range(TimeRange.D7, category="tech") == 1


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


def test_query_by_keyword_cjk_uses_like(repo):
    """中文关键词必须走 LIKE 分支 —— FTS5 unicode61 不切中文连写。

    实测旧行为: "勒索" 在含该词的语料上 MATCH 命中 0 / LIKE 命中 18,
    "漏洞" 10 / 140。本用例锁住修复后的召回。
    """
    repo.upsert_many(
        [
            _make_item("c-1", title="某团伙发起勒索软件攻击事件通报"),
            _make_item("c-2", title="供应链投毒风险预警"),
        ]
    )
    items, _ = repo.query(None, time_range=TimeRange.D7, keyword="勒索", limit=10)
    assert {it.id for it in items} == {"c-1"}

    # 部分词也应命中 (LIKE 子串语义), 而 FTS 短语匹配做不到
    items, _ = repo.query(None, time_range=TimeRange.D7, keyword="供应链投", limit=10)
    assert {it.id for it in items} == {"c-2"}


def test_count_unique_urls_honors_keyword(repo):
    """分页分母必须随 keyword 收窄, 否则搜索时 "X / Y" 会显示全窗口总数。"""
    repo.upsert_many(
        [
            _make_item("n-1", title="勒索软件样本分析笔记"),
            _make_item("n-2", title="零信任架构落地实践"),
            _make_item("n-3", title="另一篇无关文章"),
        ]
    )
    all_cnt = repo.count_unique_urls_in_range(TimeRange.D7)
    kw_cnt = repo.count_unique_urls_in_range(TimeRange.D7, keyword="勒索")
    assert all_cnt == 3
    assert kw_cnt == 1


def test_keyword_condition_branching_and_escaping(repo):
    """分支选择与 LIKE 通配符转义: % / _ 必须按字面匹配, ASCII 仍走 FTS。"""
    ascii_sql, ascii_params = repo._keyword_condition("CVE")
    assert "hotspots_fts MATCH" in ascii_sql
    assert ascii_params == ['"CVE"']

    cjk_sql, cjk_params = repo._keyword_condition("漏洞")
    assert cjk_sql.startswith("(title LIKE ?") and "ESCAPE" in cjk_sql
    assert cjk_params == ["%漏洞%", "%漏洞%"]

    # 含通配符的非 ASCII 关键词应被转义, 不退化成全表匹配
    assert repo._keyword_condition("勒索%") == (
        "(title LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\')",
        ["%勒索\\%%", "%勒索\\%%"],
    )
    assert repo._keyword_condition("") == ("", [])


# ---------------------------------------------------------------------------
# query — 游标分页
# ---------------------------------------------------------------------------
def test_query_cursor_pagination(repo):
    """10 条数据，limit=3，多次翻页无重复且能取完。"""
    items = [
        _make_item(f"p-{i:02d}", published_at=_recent_ts(hours=i))
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
    """next_cursor 形如 ``<unix_ts>_<id>``。

    v0.5 M1-Task1: 精度提升到微秒浮点 (e.g. ``1756000123.456789_abc``),
    旧整数秒格式仍可被 _parse_cursor 兼容解析。
    """
    repo.upsert_many(
        [
            _make_item("c-1", published_at=_recent_ts(hours=1)),
            _make_item("c-2", published_at=_recent_ts(hours=2)),
            _make_item("c-3", published_at=_recent_ts(hours=3)),
        ]
    )
    items, cursor = repo.query(Category.AI, limit=1)
    assert len(items) == 1
    assert cursor is not None
    # 形如 '<unix>_<id>' — v0.5 接受整数秒(旧) 与微秒浮点(新) 两种 ts 段
    parts = cursor.split("_", 1)
    assert len(parts) == 2
    assert parts[1] == items[-1].id
    # unix 部分是数值(int 或 float); 整数字面量也合法
    float(parts[0])  # raises if neither int nor float parseable


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
        "ai_security": 0,
        "security": 3,
        "finance": 0,
        "startup": 0,
        "github": 0,
        "paper": 0,
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
# Phase 21 historical_bid / bid_status 测试 — DEV-0178 已随标讯剔除移除
# ---------------------------------------------------------------------------

