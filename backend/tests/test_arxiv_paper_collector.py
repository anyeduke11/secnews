"""ArxivPaperCollector + Category.PAPER 注册点测试 (2026-09-26 论文抓取 Batch A T1)。

覆盖:
- arXiv Atom feed fixture 解析 (真实结构: entry/title/link/summary/published
  + 换行缩进标题清理 + arxiv id → item.id)
- 轮转采样: 连续两次 collect 取的领域集合不同 (mock _fetch_rss_bytes 按领域返回)
- id 落点: arxiv: 前缀 → item.id, 领域键 → item.source (设计稿 §3.2 的
  tags 三要素载体最终简化为 arxiv:<id> 单 tag, 后两元素无消费点已删)
- 注册点齐备: Category.PAPER / collectors dict / _CAT_KEYWORDS / 报表标签表 /
  crawler_sources 种子 14 行 (经 temp_db 真实跑 migration 123)

为什么这些行为重要: paper 分类要进入既有采集管线 (registry 切流按 name 对齐、
质量门禁按 category 关键词放行、报表按标签表消费), 任何一个注册点缺失都会让
论文条目在管线某处静默丢失或被误归类。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# arXiv Atom fixture — 按真实 export.arxiv.org 返回结构 (feed/entry xmlns,
# 标题内嵌换行缩进, id 为 abs 链接)。published 用近期时间, 避开
# _build_items 的 Phase 47 时效硬门禁 (早于本周一 00:00 Shanghai 拒收)。
# ---------------------------------------------------------------------------
_PUBLISHED = datetime.now(timezone.utc) - timedelta(hours=6)

ATOM_FEED_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>ArXiv Query</title>
  <id>http://arxiv.org/api/ query</id>
  <updated>2026-09-26T00:00:00-04:00</updated>
  <opensearch:totalResults xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">2</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2609.01234v1</id>
    <updated>2026-09-26T00:00:00-04:00</updated>
    <published>{published:%Y-%m-%dT%H:%M:%S-04:00}</published>
    <title>SUPERTITLE: Adversarial Robustness of
      Large Language Models
    </title>
    <summary>  This paper studies adversarial attacks and defenses
      for LLM security.  </summary>
    <author><name>Alice Security</name></author>
    <link href="http://arxiv.org/abs/2609.01234v1" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/2609.01234v1" rel="related" type="application/pdf"/>
    <category term="cs.CR" scheme="http://arxiv.org/schemas/atom"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2609.05678v2</id>
    <updated>2026-09-26T01:00:00-04:00</updated>
    <published>{published:%Y-%m-%dT%H:%M:%S-04:00}</published>
    <title>Vulnerability Detection in Source Code via
      Deep Learning
    </title>
    <summary>We benchmark vulnerability detection models on
      real-world threat intelligence datasets.</summary>
    <author><name>Bob Vuln</name></author>
    <link href="http://arxiv.org/abs/2609.05678v2" rel="alternate" type="text/html"/>
    <category term="cs.CR" scheme="http://arxiv.org/schemas/atom"/>
  </entry>
</feed>
"""


def _atom_bytes() -> bytes:
    return ATOM_FEED_TEMPLATE.format(published=_PUBLISHED).encode("utf-8")


def _make_collector():
    from backend.collectors.arxiv_paper_collector import ArxivPaperCollector

    c = ArxivPaperCollector()
    # 官方测试缝隙: 跳过质量门禁 (避免构造 QualityConfig / DB 依赖),
    # 见 backend/collectors/quality_hook.py `_skip_quality` 注释。
    c._skip_quality = True
    return c


def _patch_rss_bytes(monkeypatch):
    """隔离网络: patch _fetch_rss_bytes (fetchers.py 声明的测试缝隙),
    所有领域共用同一 fixture。

    patch 目标必须是 ArxivPaperCollector 本类 — 2026-09-27 起子类
    override 了 _fetch_rss_bytes (urllib 通道, 绕 Fastly 对 aiohttp
    指纹的 406), patch 父类 FetchersMixin 不再被 MRO 命中。"""
    from backend.collectors.arxiv_paper_collector import ArxivPaperCollector

    async def fake_fetch_rss_bytes(self, rss_url: str):
        return 200, {"Content-Type": "application/atom+xml"}, _atom_bytes()

    monkeypatch.setattr(
        ArxivPaperCollector, "_fetch_rss_bytes", fake_fetch_rss_bytes
    )


# ---------------------------------------------------------------------------
# 1. Atom 解析 + tags 映射
# ---------------------------------------------------------------------------
def test_atom_parse_title_cleanup_and_tags(tmp_path, monkeypatch):
    """Atom entry → HotspotItem: 标题压平 / id=arxiv: 前缀 / source=领域键。"""
    _patch_rss_bytes(monkeypatch)
    collector = _make_collector()
    source = dict(collector.sources[0])  # "AI" 领域

    items, sr = asyncio.run(collector.fetch_source(source))

    assert sr.error_msg is None, f"fetch failed: {sr.error_msg}"
    assert len(items) == 2
    first = items[0]
    # 标题换行缩进被清理为单空格
    assert first.title == "SUPERTITLE: Adversarial Robustness of Large Language Models"
    # tags[0] 落 item.id (arxiv: 前缀 + arXiv 论文 ID)
    assert first.id == "arxiv:2609.01234v1"
    # tags[1] 的领域键落 item.source
    assert first.source == "AI"
    assert first.category.value == "paper"
    # abs 页链接 (非 pdf link)
    assert str(first.url).rstrip("/").endswith("2609.01234v1")
    assert first.published_at is not None


def test_paper_tags_prefixes():
    """arxiv:<id> 稳定 id 映射 (设计稿 §3.2 tags 载体简化后仅存的主 tag)。"""
    from backend.collectors.arxiv_paper_collector import _arxiv_id_from_url

    assert _arxiv_id_from_url("http://arxiv.org/abs/2609.01234v1") == "2609.01234v1"


def test_non_abs_url_falls_back_to_url_fingerprint_id(tmp_path, monkeypatch):
    """非 abs 链接 (提取失败) 回退基类 URL 指纹 ID, 不造出 arxiv: 空前缀。"""
    _patch_rss_bytes(monkeypatch)
    collector = _make_collector()
    raw = [{
        "title": "A Survey of LLM Security",
        "url": "https://example.org/paper/123",
        "summary": "s",
        "published_at": datetime.now(timezone.utc),
    }]
    items = collector._build_items(raw, {"name": "AI"})
    assert len(items) == 1
    assert not items[0].id.startswith("arxiv:")


# ---------------------------------------------------------------------------
# 2. 轮转采样
# ---------------------------------------------------------------------------
def _collect_domains(collector, feed_by_source: dict[str, bytes]) -> set[str]:
    """跑一轮 collect, 返回本轮实际抓取的领域键集合 (按 source name 打标)。

    真实抓取窗口由 collect() 内部的 _load_sources_from_registry 推进,
    这里不做任何手动游标操作。

    fake 按 rss_url 精确映射 fixture (DEV-0233 收口: 节拍锁串行化后,
    旧实现经实例属性 `_current_source_name` 传名存在跨任务竞态 — 前一
    任务的 finally 清空会覆盖后一任务已设置的名称; 按 url 查表无共享
    状态且断言更强, 每个领域 URL 只命中自己的 fixture)。
    """
    from backend.collectors.arxiv_paper_collector import (
        PAPER_SOURCES,
        ArxivPaperCollector,
    )

    # 节拍锁为真实出网限速设计 (3s/请求), mock 场景置 0 避免测试空睡
    ArxivPaperCollector._PACE_INTERVAL = 0
    feed_by_url = {
        s["rss_url"]: feed_by_source[s["name"]] for s in PAPER_SOURCES
    }

    async def fake_fetch_rss_bytes(self, rss_url: str):
        feed = feed_by_url.get(rss_url)
        assert feed is not None, f"unexpected rss_url {rss_url[:80]!r}"
        return 200, {"Content-Type": "application/atom+xml"}, feed

    import unittest.mock as mock

    with mock.patch.object(
        ArxivPaperCollector, "_fetch_rss_bytes", fake_fetch_rss_bytes
    ):
        items = asyncio.run(collector.collect())

    # 有产出 (每源 fixture 2 条 × 3 源 = 6 ≥ min_items_threshold=3)
    assert items, "collect returned no items — 轮转窗口源未被抓取"
    return {it.source for it in items}


def test_rotation_two_rounds_pick_different_domains(temp_db, monkeypatch):
    """连续两次 collect: 取的领域集合不同, 游标推进 +3 (mod 14)。"""
    from backend.collectors.arxiv_paper_collector import PAPER_DOMAIN_QUERIES

    feed_by_source = {
        d: _atom_bytes().replace(b"2609.01234", f"2609.{i:05d}".encode())
        for i, d in enumerate(PAPER_DOMAIN_QUERIES)
    }

    collector = _make_collector()
    round1 = _collect_domains(collector, feed_by_source)
    assert len(round1) == 3, f"每轮应取 3 个领域, 实际 {round1}"

    round2 = _collect_domains(collector, feed_by_source)
    assert len(round2) == 3
    assert round1 != round2, "连续两轮的领域集合应不同 (轮转采样失效)"


def test_rotation_covers_all_domains_over_cycles(temp_db):
    """游标推进 mod 14: 若干轮后窗口并集覆盖全部 14 领域。"""
    from backend.collectors.arxiv_paper_collector import PAPER_DOMAIN_QUERIES

    collector = _make_collector()
    seen: set[str] = set()
    for _ in range(5):  # 5 轮 × 3 = 15 ≥ 14
        seen.update(collector._next_round_domains())
    assert seen == set(PAPER_DOMAIN_QUERIES)


# ---------------------------------------------------------------------------
# 3. 注册点齐备
# ---------------------------------------------------------------------------
def test_category_paper_registered():
    """Category.PAPER 枚举 + from_str 往返。"""
    from backend.domain.enums import Category

    assert Category.PAPER.value == "paper"
    assert Category.from_str("paper") is Category.PAPER


def test_collectors_dict_has_paper():
    """collection_service.collectors dict 含 PAPER → ArxivPaperCollector。"""
    from backend.collectors.arxiv_paper_collector import ArxivPaperCollector
    from backend.domain.enums import Category
    from backend.services.collection_service import CollectionService

    svc = CollectionService()
    assert Category.PAPER in svc.collectors
    collectors = svc.collectors[Category.PAPER]
    assert len(collectors) == 1
    assert isinstance(collectors[0], ArxivPaperCollector)


def test_keywords_gate_lets_security_paper_titles_through():
    """paper 关键词表: 安全论文标题过 _title_relevant, 无关标题被拦。"""
    from backend.collectors.keywords import _is_title_relevant_to_category

    assert _is_title_relevant_to_category(
        "Adversarial Robustness of Large Language Models", "paper"
    )
    assert _is_title_relevant_to_category(
        "Vulnerability Detection in Source Code via Deep Learning", "paper"
    )
    assert _is_title_relevant_to_category(
        "A Survey of Threat Intelligence Sharing", "paper"
    )
    # 无任何学术/安全词 → 拦 (这张表是 paper 分类的入管白名单)
    assert not _is_title_relevant_to_category("My Cat is Cute", "paper")


def test_report_services_label_tables_have_paper():
    """三个 report service 的标签/顺序/文案表都登记 paper (缺 ORDER 会被
    CATEGORY_ORDER 驱动的循环整域跳过)。"""
    from backend.services import (
        daily_report_overview_service,
        monthly_report_service,
        weekly_report_overview_service,
    )

    for mod in (
        daily_report_overview_service,
        weekly_report_overview_service,
        monthly_report_service,
    ):
        assert mod.CATEGORY_LABELS.get("paper") == "论文", mod.__name__
        assert "paper" in mod.CATEGORY_ORDER, mod.__name__


def test_crawler_sources_seed_14_rows(temp_db):
    """migration 123 种子: 14 行 paper 源, name 与 sources 领域键对齐,
    feed_url (registry → rss_url 路由键) 与 api_url 均为领域 query。"""
    from backend.collectors.arxiv_paper_collector import PAPER_DOMAIN_QUERIES
    from backend.repository.db import get_connection

    conn = get_connection()
    rows = conn.execute(
        "SELECT id, category, name, kind, url, feed_url, api_url, enabled, "
        "network_zone FROM crawler_sources WHERE category = 'paper'"
    ).fetchall()

    assert len(rows) == 14
    by_name = {r["name"]: r for r in rows}
    # 注册行 name 必须与 collector sources 领域键一一对齐 (切流机制按 name 匹配)
    assert set(by_name) == set(PAPER_DOMAIN_QUERIES)
    for name, r in by_name.items():
        assert r["kind"] == "rss"
        assert r["enabled"] == 1
        assert r["network_zone"] == "international"
        assert r["feed_url"] == PAPER_DOMAIN_QUERIES[name], name
        assert r["api_url"] == PAPER_DOMAIN_QUERIES[name], name
        assert r["id"] == f"paper:{name}"


def test_registry_rotation_window_applies(temp_db):
    """registry 装载路径应用轮转窗口: 装载结果只含本轮 3 领域。"""
    from backend.collectors.arxiv_paper_collector import PAPER_DOMAIN_QUERIES

    collector = _make_collector()
    collector._domain_cursor = 0
    # 手动按 cursor=0 算期望窗口 (不推进游标; 真实推进发生在装载内部)
    keys = list(PAPER_DOMAIN_QUERIES)
    expected_window = set(keys[:3])

    loaded = collector._load_sources_from_registry(only_source=None)
    assert loaded is not None
    assert {s["name"] for s in loaded} == expected_window
    assert all(s.get("rss_url") for s in loaded), "registry 行应带 rss_url (走 _fetch_rss)"


def test_paper_domain_queries_shape():
    """14 领域 query 形状: export.arxiv.org API + sortBy=submittedDate
    + max_results=20 (sortBy 合法值见 arXiv API 手册; DEV-0233 真实拉取
    验证发现 `submitted` 非法 → Error entry feed, 精确断言防回退)。
    https 直连 (127: http 会 301 多一跳, 且低信誉链路更易触 Fastly 限流)。"""
    from backend.collectors.arxiv_paper_collector import PAPER_DOMAIN_QUERIES

    assert len(PAPER_DOMAIN_QUERIES) == 14
    for domain, url in PAPER_DOMAIN_QUERIES.items():
        assert url.startswith("https://export.arxiv.org/api/query?search_query=")
        assert "sortBy=submittedDate" in url
        assert "sortBy=submitted&" not in url
        assert "sortOrder=descending" in url
        assert url.endswith("max_results=20")
    # 设计稿 §2 抽样: AI 多 cat OR / 漏洞治理 短语 AND / AI安全 对抗交叉
    assert "cat:cs.AI" in PAPER_DOMAIN_QUERIES["AI"]
    assert "cat:cs.CL" in PAPER_DOMAIN_QUERIES["AI"]
    assert "vulnerability" in PAPER_DOMAIN_QUERIES["漏洞治理"]
    assert "adversarial" in PAPER_DOMAIN_QUERIES["AI安全"]
