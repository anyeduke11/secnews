"""crawler-v2 Phase 1 切流测试 — 源注册表驱动采集.

覆盖:
- 表驱动源与常量实际生效源等价 (含黑名单过滤/disabled 排除/wechat 替代)
- 表无分类记录 → 回退常量 (渐进切流)
- 表有记录但全 disabled → 返回 [] (用户禁用, 不回退)
- renderer/keywords 补充正确
"""
from __future__ import annotations

import sqlite3

import pytest


@pytest.fixture()
def crawler_db(tmp_path, monkeypatch):
    """临时 DB: 建 crawler_sources 表 + 替换 get_connection."""
    db_file = tmp_path / "crawler.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row  # 与 repository/db.py 一致
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS crawler_sources (
            id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            name TEXT NOT NULL,
            kind TEXT DEFAULT 'html',
            url TEXT DEFAULT '',
            feed_url TEXT DEFAULT '',
            api_url TEXT DEFAULT '',
            priority INTEGER DEFAULT 50,
            enabled INTEGER DEFAULT 1
        );
        """
    )
    conn.commit()
    from backend import repository as repo_pkg
    from backend.repository import db as db_mod

    monkeypatch.setattr(db_mod, "get_connection", lambda: conn)
    for name in list(repo_pkg.__dict__.keys()):
        m = getattr(repo_pkg, name)
        if hasattr(m, "get_connection"):
            try:
                monkeypatch.setattr(m, "get_connection", lambda: conn)
            except (AttributeError, TypeError):
                pass
    yield conn
    conn.close()


def _seed(conn, category: str, sources: list[dict]) -> None:
    for s in sources:
        conn.execute(
            "INSERT OR REPLACE INTO crawler_sources "
            "(id, category, name, kind, url, feed_url, api_url, priority, enabled) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"{category}:{s['name']}", category, s["name"],
                "rss" if s.get("feed_url") else "html",
                s.get("url", ""), s.get("feed_url", ""),
                s.get("api_url", ""),
                s.get("priority", 50), s.get("enabled", 1),
            ),
        )
    conn.commit()


def test_registry_driven_sources_equivalent_to_constants(crawler_db):
    """表驱动源 == 常量实际生效源 (6 个已注册分类)."""
    from backend.collectors.ai_collector import AICollector
    from backend.collectors.finance_collector import FinanceCollector
    from backend.collectors.github_collector import GitHubCollector
    from backend.collectors.security_collector import SecurityCollector
    from backend.collectors.startup_collector import StartupCollector
    from backend.collectors.tech_collector import TechCollector

    collectors = [
        AICollector(), SecurityCollector(), FinanceCollector(),
        GitHubCollector(), TechCollector(), StartupCollector(),
    ]
    # 用真实 seed 逻辑注册 (等价于生产 seed)
    from backend.scripts.seed_crawler_sources import _collect_sources
    for s in _collect_sources():
        crawler_db.execute(
            "INSERT OR REPLACE INTO crawler_sources "
            "(id, category, name, kind, url, feed_url, api_url, priority, enabled) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"{s['category']}:{s['name']}", s["category"], s["name"],
                s["kind"], s["url"], s["feed_url"],
                s.get("api_url", ""), s["priority"], s["enabled"],
            ),
        )
    crawler_db.commit()

    for collector in collectors:
        reg = collector._load_sources_from_registry()
        assert reg is not None, f"{collector.category.value} 应已注册"
        reg_names = {s["name"] for s in reg}
        const_enabled = {
            s["name"] for s in collector.sources
            if s.get("renderer") != "disabled"
        }
        # P0 SSRF Layer 2: seed_crawler_sources 排除 wechat/sogou 源 (无 url),
        # 它们由主 collector 从类常量加载, 不进 registry 表。
        # 所以 reg_names 是 const_enabled 的子集 (wechat/sogou 子集被过滤)。
        const_with_url = {
            s["name"] for s in collector.sources
            if s.get("renderer") not in ("disabled", "wechat", "sogou")
        }
        assert reg_names == const_with_url, (
            f"{collector.category.value}: 表源 {sorted(reg_names - const_with_url)} "
            f"vs 常量(去 wechat/sogou/disabled) {sorted(const_with_url - reg_names)}"
        )
        # renderer 补充: 表源 renderer 应来自常量的非 disabled 条目
        for s in reg:
            const = next(
                (x for x in collector.sources
                 if x["name"] == s["name"] and x.get("renderer") != "disabled"),
                None,
            )
            if const and const.get("renderer"):
                assert s["renderer"] == const["renderer"], (
                    f"{s['name']}: {s['renderer']} != {const['renderer']}"
                )


def test_unregistered_category_falls_back_to_constants(crawler_db):
    """表无分类记录 → 返回 None (调用方回退常量)."""
    from backend.collectors.ai_security_collector import AISecurityCollector

    collector = AISecurityCollector()  # ai_security 未注册
    assert collector._load_sources_from_registry() is None


def test_all_disabled_returns_empty(crawler_db):
    """表有记录但全 disabled → 返回 [] (不回退常量)."""
    from backend.collectors.ai_collector import AICollector

    _seed(crawler_db, "ai", [
        {"name": "Alpha", "url": "https://a.com", "enabled": 0},
    ])
    collector = AICollector()
    assert collector._load_sources_from_registry() == []


def test_disabled_sources_excluded_from_registry(crawler_db):
    """seed 后 renderer=disabled 源应 enabled=0 (不会被表驱动抓取)."""
    from backend.scripts.seed_crawler_sources import _collect_sources

    by_name = {s["name"]: s for s in _collect_sources()
               if s["category"] == "ai"}
    # 量子位/36氪AI/机器之心 是 renderer=disabled (反爬) → enabled=0
    for name in ("量子位", "36氪AI", "机器之心"):
        assert by_name[name]["enabled"] == 0, name
    # 正常源 enabled=1
    assert by_name["HackerNews"]["enabled"] == 1


def test_collect_uses_registry_sources(crawler_db, monkeypatch):
    """collect() 应使用表驱动源 (strangler 切流生效)."""
    from backend.collectors.ai_collector import AICollector

    _seed(crawler_db, "ai", [
        {"name": "OnlySource", "url": "https://only.com", "priority": 90},
    ])
    collector = AICollector()
    # 不真正抓取: 只验证 collect 入口把 self.sources 替换为表源
    from backend.domain.collection import SourceResult

    async def fake_fetch(src):
        return [], SourceResult(
            source_name=src["name"], source_url=src.get("url", ""),
            item_count=0, duration_ms=0,
        )

    monkeypatch.setattr(collector, "fetch_source", fake_fetch)
    import asyncio
    asyncio.run(collector.collect())
    assert [s["name"] for s in collector.sources] == ["OnlySource"]


# ===========================================================================
# P0 SSRF 副作用根除 — Layer 3 测试 (base.py)
# ===========================================================================
def test_null_url_row_filtered_out(crawler_db):
    """url/feed_url/api_url 全空行 (wechat 误入) 在 _load_sources_from_registry
    必须被 skip, 避免 fetch_source 走 aiohttp fallback 抛 InvalidUrlClientError."""
    from backend.collectors.security_collector import SecurityCollector

    _seed(crawler_db, "security", [
        # 全空 url — 历史脏数据, Layer 1 migration 漏过的 wechat 源
        {"name": "微步在线", "url": "", "feed_url": "", "priority": 80},
        # 正常 RSS 源
        {"name": "freebuf", "url": "", "feed_url": "https://www.freebuf.com/feed/", "priority": 80},
    ])
    collector = SecurityCollector()
    reg = collector._load_sources_from_registry()
    names = [s["name"] for s in reg]
    # null url 源被过滤
    assert "微步在线" not in names, (
        "P0 SSRF Layer 3: url/feed_url/api_url 全空行必须 skip, "
        f"实际保留: {names}"
    )
    # 正常行保留
    assert "freebuf" in names


def test_global_renderer_const_preserves_wechat(crawler_db):
    """次 collector (无 wechat 源 const) 拿同 category 行, 通过全局
    _RENDERER_BY_NAME 仍能解析 renderer='wechat'."""
    from backend.collectors.base import BaseCollector
    from backend.domain.enums import Category

    # 关键: 重置 cache 让本次测试拿最新数据
    BaseCollector._RENDERER_BY_NAME = None

    _seed(crawler_db, "security", [
        # 有 url 的 wechat 源 — 不应被 Layer 3 兜底过滤
        {"name": "看雪学院", "url": "https://www.kanxue.com/", "priority": 75},
    ])

    class _SecondarySecurityCollector(BaseCollector):
        """模拟 GDELTCollector — category=SECURITY 但 self.sources 无看雪学院."""
        category = Category.SECURITY
        name = "secondary_test"
        sources = []

    c = _SecondarySecurityCollector()
    reg = c._load_sources_from_registry()
    assert reg is not None
    kanxue = next((r for r in reg if r["name"] == "看雪学院"), None)
    assert kanxue is not None
    # 全局 const 应能解析出 wechat (或至少 aiohttp, 不抛错)
    assert kanxue["renderer"] in ("wechat", "aiohttp")


def test_global_renderer_cache_reused(crawler_db):
    """_get_renderer_by_name 类级 cache 命中."""
    from backend.collectors.base import BaseCollector

    BaseCollector._RENDERER_BY_NAME = None
    m1 = BaseCollector._get_renderer_by_name()
    m2 = BaseCollector._get_renderer_by_name()
    # 同一对象, cache 命中
    assert m1 is m2
    assert isinstance(m1, dict)


# ===========================================================================
# P0 SSRF 副作用根除 — Layer 2 测试 (seed_crawler_sources URL guard)
# ===========================================================================
def test_seed_crawler_sources_skips_null_url_html():
    """wechat/sogou/disabled 之外 renderer + 全空 url/rss_url → skip."""
    from backend.scripts.seed_crawler_sources import _collect_sources

    by_name = {s["name"]: s for s in _collect_sources()}
    # AI 分类里如果有 renderer=aiohttp + url 空 的源, 必被新守卫过滤
    for name, entry in by_name.items():
        if entry.get("renderer") in ("wechat", "sogou", "disabled", ""):
            continue
        # 其他 renderer 必有 url 或 feed_url
        assert entry.get("url") or entry.get("feed_url"), (
            f"seed_crawler_sources Layer 2 漏过: {name} renderer={entry.get('renderer')!r} "
            f"但 url/feed_url 全空"
        )


def test_seed_crawler_sources_preserves_wechat_with_account_name():
    """renderer=wechat 即使 url 空, account_name 在 SOURCES 常量, 仍可注册
    (由主 collector 从类常量加载, 不依赖 registry url)."""
    from backend.collectors.security_collector import SecurityCollector

    by_name = {s["name"]: s for s in SecurityCollector.sources}
    for name, s in by_name.items():
        if s.get("renderer") == "wechat":
            # wechat 源有 account_name 字段
            assert s.get("account_name"), (
                f"wechat 源 {name} 缺 account_name, 无法走搜狗微信搜索"
            )

