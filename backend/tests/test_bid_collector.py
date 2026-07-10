"""BidCollector 单元测试（Phase 3 + Phase 9 改造）。

覆盖：
- ``category`` 设置为 ``Category.BID``
- ``_fallback()`` 返回 ≥ ``min_items_threshold`` 条且全部为 BID 分类
- Phase 9: BID_SOURCES 扩充到 30+ 渠道，覆盖 skillhub 推荐 50+ 渠道关键子集
- Phase 9: SECURITY_KEYWORDS 包含四线关键词（安全服务/产品/运维/行业）
- Phase 9: is_security_bid 正确判断网安相关/无关
- Phase 9: _is_relevant 过滤无关采购
- Phase 9: _parse_html 应用关键词过滤
- Phase 9: fallback 数据全部为网安/AI安全相关
"""
from __future__ import annotations

from backend.collectors.base import HAS_PROXY
from backend.collectors.bid_collector import (
    BID_SOURCES,
    BidCollector,
    PROCUREMENT_KEYWORDS,
    SECURITY_KEYWORDS,
    SECURITY_KEYWORD_SET,
    is_security_bid,
)
from backend.domain.enums import Category
from backend.services.collection_service import CollectionService


# ---------------------------------------------------------------------------
# 基本属性
# ---------------------------------------------------------------------------
def test_bid_collector_has_category():
    assert BidCollector().category is Category.BID


def test_bid_collector_name():
    assert BidCollector().name == "bid"


# ---------------------------------------------------------------------------
# _fallback 行为 (Phase 13 硬约束: fallback 必须返回空列表)
# ---------------------------------------------------------------------------
def test_bid_collector_fallback_returns_empty():
    """Phase 13 硬约束 (SPEC §3.3.1): BidCollector 不实现 _fallback。
    BaseCollector 默认 _fallback() 返回 [],子类继承即可。
    """
    c = BidCollector()
    items = c._fallback()
    assert items == [], (
        f"BidCollector._fallback() 返回 {len(items)} 条合成数据,违反 Phase 13 硬约束"
    )


# ---------------------------------------------------------------------------
# BID_SOURCES 覆盖度（Phase 9 关键）
# ---------------------------------------------------------------------------
def test_bid_sources_count():
    """Phase 9: BID_SOURCES 应扩充到 30+ 渠道。"""
    assert len(BID_SOURCES) >= 30, (
        f"BID_SOURCES 只有 {len(BID_SOURCES)} 个,期望 ≥ 30"
    )


def test_bid_sources_have_required_fields():
    """每个 source 必须有 name/url/score/keywords 字段。"""
    for s in BID_SOURCES:
        assert "name" in s and s["name"], f"source 缺 name: {s}"
        assert "url" in s and s["url"], f"source 缺 url: {s}"
        assert "score" in s, f"source 缺 score: {s}"
        assert 0 <= s["score"] <= 100, f"score 越界: {s}"
        assert "keywords" in s, f"source 缺 keywords: {s}"


def test_bid_sources_cover_all_priority_levels():
    """Phase 9: 必须覆盖 P0 国家级 + P1 金融/能源/电信 + P2 商业聚合。"""
    urls_str = " ".join(s["url"] for s in BID_SOURCES)
    keywords_str = " ".join(
        " ".join(s.get("keywords", [])) for s in BID_SOURCES
    )

    # P0 国家级（必须有 ccgp.gov.cn / cebpubservice.com / ggzy.gov.cn）
    assert "ccgp.gov.cn" in urls_str
    assert "cebpubservice.com" in urls_str
    assert "ggzy.gov.cn" in urls_str

    # P1 金融（必须有 cfcpn.com + szse 或 sse）
    assert "cfcpn.com" in urls_str
    assert "szse.cn" in urls_str or "sse.com.cn" in urls_str

    # P1 能源电力（必须有 ecp.sgcc.com.cn + bidding.csg.cn）
    assert "ecp.sgcc.com.cn" in urls_str
    assert "bidding.csg.cn" in urls_str

    # P1 电信（必须包含 移动/电信/联通 之一）
    has_telecom = (
        "10086.cn" in urls_str
        or "chinatelecom" in urls_str
        or "chinaunicombidding" in urls_str
    )
    assert has_telecom, "缺电信运营商渠道"

    # P2 商业聚合（必须有 bidcenter + 千里马 / 乙方宝 之一）
    assert "bidcenter.com.cn" in urls_str
    assert (
        "qianlima.com" in urls_str
        or "yifangbao.com" in urls_str
    ), "缺商业聚合渠道"

    # 关键词标注
    assert "bid" in keywords_str


# ---------------------------------------------------------------------------
# Phase 19: v1.6.3 补全 16 源 + search 路由
# ---------------------------------------------------------------------------
def test_bid_sources_have_phase19_sources():
    """Phase 19 补全 v1.6.3 16 源。"""
    urls_str = " ".join(s["url"] for s in BID_SOURCES)
    # P1 金融缺口
    assert "pms.adbc.com.cn" in urls_str, "缺中国农业发展银行"
    assert "cfxcredit.com" in urls_str, "缺银保信"
    assert "chinaunionpay.com" in urls_str, "缺中国银联"
    assert "zgzx-pa.com.cn" in urls_str, "缺证保信"
    # P1 能源缺口
    assert "ec.chng.com.cn" in urls_str, "缺华能"
    assert "cdt-ec.com" in urls_str, "缺大唐"
    assert "chdtp.com" in urls_str, "缺华电"
    assert "ebid.sinochemitc.com" in urls_str, "缺中化"
    assert "ygcg.szexgrp.com" in urls_str, "缺深圳阳光"
    # P2 商业聚合缺口
    assert "okcis.cn" in urls_str, "缺 okcis"
    assert "bidizhaobiao.com" in urls_str, "缺比地"
    assert "bidchance.com" in urls_str, "缺元博"
    assert "chinabidding.mofcom.gov.cn" in urls_str, "缺 mofcom"
    assert "chinabidding.org.cn" in urls_str, "缺 chinabidding.org.cn"
    # P3 辅助缺口
    assert "chinamoney.com.cn" in urls_str, "缺外汇交易中心"


def test_bid_phase19_sources_have_search_renderer():
    """Phase 19 新增 16 源的 renderer 必须为 'search'（走 DDG 绕反爬）。

    setdefault('renderer', 'crawl4ai') 不会覆盖显式设的 'search'。
    """
    search_sources = [s for s in BID_SOURCES if s.get("renderer") == "search"]
    assert len(search_sources) >= 16, (
        f"renderer='search' 源应 ≥ 16,实际 {len(search_sources)}"
    )
    # 验证关键源都在
    search_names = {s["name"] for s in search_sources}
    expected = {
        "中国农业发展银行集中采购", "银保信", "中国银联采购",
        "华能电子商务平台", "大唐电子商务平台", "华电电子商务平台",
        "中化商务电子招投标", "深圳阳光采购平台",
        "招标采购导航网", "比地招标网", "元博招标网",
        "中国国际招标网", "中国政府采购招标网",
        "中国外汇交易中心",
    }
    missing = expected - search_names
    assert not missing, f"Phase 19 search 源缺失: {missing}"


def test_bid_old_sources_still_use_crawl4ai():
    """非 Phase 19 的源仍走 crawl4ai（向后兼容）。"""
    crawl4ai_sources = [s for s in BID_SOURCES if s.get("renderer") == "crawl4ai"]
    assert len(crawl4ai_sources) >= 20, (
        f"renderer='crawl4ai' 源应 ≥ 20(老源),实际 {len(crawl4ai_sources)}"
    )


# ---------------------------------------------------------------------------
# SECURITY_KEYWORDS 四线体系
# ---------------------------------------------------------------------------
def test_security_keywords_has_four_lines():
    """Phase 9: SECURITY_KEYWORDS 必须包含 4 条业务线。"""
    expected_lines = {"安全服务线", "安全产品线", "运维/平台线", "行业搜索线"}
    actual_lines = set(SECURITY_KEYWORDS.keys())
    assert expected_lines.issubset(actual_lines), (
        f"缺业务线: {expected_lines - actual_lines}"
    )


def test_security_keywords_each_line_non_empty():
    """每条业务线至少 5 个关键词。"""
    for line, words in SECURITY_KEYWORDS.items():
        assert len(words) >= 5, f"{line} 关键词不足 5 个: {words}"


def test_security_keyword_set_non_empty():
    """SECURITY_KEYWORD_SET 必须非空。"""
    assert len(SECURITY_KEYWORD_SET) > 0


def test_security_keywords_includes_ai_safety():
    """Phase 9: 关键词必须包含 AI 安全/大模型安全。"""
    all_words = " ".join(
        kw for words in SECURITY_KEYWORDS.values() for kw in words
    )
    assert "AI安全" in all_words or "大模型安全" in all_words, (
        f"缺 AI 安全关键词"
    )


def test_security_keywords_includes_mainstream_terms():
    """必须包含主流网安关键词:防火墙/等保/密评/数据安全/SOC。"""
    all_words = set()
    for words in SECURITY_KEYWORDS.values():
        all_words.update(words)
    expected = {
        "防火墙", "等保", "密评", "数据安全",
        "SOC", "渗透测试", "态势感知", "零信任",
    }
    missing = expected - all_words
    assert not missing, f"缺关键词: {missing}"


# ---------------------------------------------------------------------------
# is_security_bid 判断
# ---------------------------------------------------------------------------
def test_is_security_bid_positive_cases():
    """命中关键词应返回 True。"""
    cases = [
        "等保 2.0 三级测评项目",
        "防火墙采购公告",
        "密评服务项目招标",
        "数据安全治理平台",
        "SOC 安全运营中心",
        "渗透测试服务",
        "零信任架构",
        "AI 大模型安全防护",
        "DLP 数据防泄漏",
        "态势感知系统建设",
    ]
    for text in cases:
        assert is_security_bid(text), f"应判 True: {text!r}"


def test_is_security_bid_negative_cases():
    """不命中应返回 False。"""
    cases = [
        "办公楼装修工程招标",
        "打印机耗材采购",
        "办公电脑采购项目",
        "园林绿化服务",
        "员工食堂餐饮服务",
        "汽车维修服务",
        # Phase 18 黑名单新增 — 售后 / 车辆保养
        "服务器售后保修服务项目",
        "车辆保养维修招标",
        "检测线设备采购",
        "公交车验车服务",
        "客服呼叫中心外包",
        "话务外包服务",
        "",  # 空串
    ]
    for text in cases:
        assert not is_security_bid(text), f"应判 False: {text!r}"


# ---------------------------------------------------------------------------
# _is_relevant / _parse_html 过滤
# ---------------------------------------------------------------------------
def test_is_relevant_filters_unrelated():
    """_is_relevant 正确过滤无关采购。"""
    c = BidCollector()
    assert c._is_relevant("防火墙采购项目") is True
    assert c._is_relevant("网络安全运维") is True
    assert c._is_relevant("员工食堂服务") is False
    assert c._is_relevant("空调维修") is False


def test_parse_html_filters_unrelated_items():
    """_parse_html 模拟招标页面,过滤无关条目。"""
    c = BidCollector()
    source = {
        "name": "测试",
        "url": "https://example.com",
    }
    html = """
    <html><body>
    <a href="/bid/1">国家医疗保障局网络安全运维服务项目</a>
    <a href="/bid/2">防火墙设备采购公告</a>
    <a href="/bid/3">员工食堂餐饮服务</a>
    <a href="/bid/4">办公电脑打印机采购</a>
    <a href="/bid/5">等保 2.0 测评服务</a>
    <a href="/bid/6">空调维修项目</a>
    <a href="/bid/7">零信任安全架构改造</a>
    </body></html>
    """
    items = c._parse_html(html, source)
    urls = [it.get("url", "") for it in items]
    titles = [it.get("title", "") for it in items]

    # 网安相关应保留（1, 2, 5, 7）
    assert any("1" in u for u in urls), "网安项目 1 应保留"
    assert any("2" in u for u in urls), "网安项目 2 应保留"
    assert any("5" in u for u in urls), "网安项目 5 应保留"
    assert any("7" in u for u in urls), "网安项目 7 应保留"

    # 无关采购应过滤（3, 4, 6）
    assert not any("3" in u for u in urls), "食堂服务 3 应过滤"
    assert not any("4" in u for u in urls), "办公采购 4 应过滤"
    assert not any("6" in u for u in urls), "空调维修 6 应过滤"

    # 全部为网安相关
    for t in titles:
        assert is_security_bid(t), f"过滤后仍含非网安标题: {t!r}"


# ---------------------------------------------------------------------------
# CollectionService 注册
# ---------------------------------------------------------------------------
def test_bid_collector_registers_in_collection_service():
    svc = CollectionService()
    assert Category.BID in svc.collectors
    assert isinstance(svc.collectors[Category.BID], BidCollector)
