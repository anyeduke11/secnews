"""招标资讯热点数据采集器（DEPRECATED — Phase 1.6 Crawler v2）。

**DEPRECATED**: 此模块将在 Crawler v2 完全上线后停止写入新数据。
当前仍运行以维持兼容性（Phase 1.6: 仍运行但不写入新数据）。
新架构下标讯抓取将走 `crawler_sources` 源注册表 + `parsers/bid/` 独立 parser。

继承 :class:`BaseCollector`：

- ``category``  : ``Category.BID``
- ``sources``   : 30+ 国家级 / 行业级 / 商业级招标平台（覆盖 skillhub 网安标讯助手推荐渠道）
- ``timeout``   : 25s
- ``max_items`` : 40

Phase 9 改造：
1. 渠道扩充：8 → 30+ 源（金融/能源/电信/医疗/交通/商业聚合全覆盖）
2. 关键词过滤：四线 AND/OR 体系（安全服务线 / 安全产品线 / 运维平台线 / 行业搜索线），
   只保留网络安全/AI安全相关的招标，避免大量无关采购信息
3. 抓取过滤：在 ``_parse_html`` 中应用关键词过滤

Phase 13 硬约束: 撤销 Phase 12 的 Google 搜索 fallback 方案。用户明确反
对"把搜索工作推给用户"。源全部失败时直接返回空列表,UI 显示
"该分类暂无可用资讯"。详细约束见 SPEC §3。

参考 skillhub 网安标讯助手：
    https://skillhub.cn/skills/bid-news-collection-light
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from backend.collectors.base import UA as _UA
from backend.collectors.base import BaseCollector
from backend.collectors.bid_utils import (
    PROCUREMENT_KEYWORDS,
    SECURITY_KEYWORD_SET,
    SECURITY_KEYWORDS,
    is_security_bid,
)
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.parsers.crawl4ai_parser import CrawlResult

# ---------------------------------------------------------------------------
# 30+ 招标渠道（覆盖 skillhub 推荐 50+ 渠道的关键子集）
# ---------------------------------------------------------------------------
# P0 国家级官方平台
# P1 金融行业
# P1 能源电力
# P1 电信运营商
# P1 政府机构
# P2 医疗教育
# P2 交通制造
# P2 商业聚合
# P3 辅助渠道
BID_SOURCES: list[dict] = [
    # ===== P0 国家级官方平台（5） =====
    {
        "name": "中国政府采购网",
        "url": "https://www.ccgp.gov.cn/cggg/zygg/",
        "score": 80,
        "keywords": ["bid", "government"],
    },
    {
        "name": "招标投标公共服务平台",
        "url": "https://www.cebpubservice.com/ggxx/",
        "score": 80,
        "keywords": ["bid", "public"],
    },
    {
        "name": "全国公共资源交易平台",
        "url": "https://www.ggzy.gov.cn/info/zbgg",
        "score": 80,
        "keywords": ["bid", "public"],
    },
    {
        "name": "中央政府采购网",
        "url": "https://www.zycg.gov.cn/freecms/site/zycg/ggxx/info/",
        "score": 78,
        "keywords": ["bid", "government"],
    },
    {
        "name": "中国采购与招标网",
        "url": "https://www.chinabidding.com.cn/zbgg/",
        "score": 75,
        "keywords": ["bid", "platform"],
    },
    # ===== P1 金融行业（6+6=12 源 — Phase 16 补全表格 P1 缺口） =====
    {
        "name": "深交所采购信息",
        "url": "https://www.szse.cn/disclosure/notice/general/",
        "score": 80,
        "keywords": ["bid", "finance"],
    },
    {
        "name": "上交所采购信息",
        "url": "https://www.sse.com.cn/services/trading/business/",
        "score": 80,
        "keywords": ["bid", "finance"],
    },
    {
        "name": "中金所采购公告",
        "url": "https://www.cffex.com.cn/",
        "score": 78,
        "keywords": ["bid", "finance"],
    },
    {
        "name": "国家开发银行采购",
        "url": "https://www.cdb.cn/",
        "score": 78,
        "keywords": ["bid", "finance"],
    },
    {
        "name": "成方金融采购网",
        "url": "https://www.cfid.org.cn/",
        "score": 76,
        "keywords": ["bid", "finance"],
    },
    {
        "name": "金融采购网",
        "url": "https://www.cfcpn.com/",
        "score": 75,
        "keywords": ["bid", "finance"],
    },
    # Phase 16 新增 — 覆盖表格 P1 金融缺口
    {
        "name": "中国人民银行集中采购中心",  # 表格 "央行(jzcg)"
        "url": "https://jzcg.pbc.gov.cn/",
        "score": 80,
        "keywords": ["bid", "finance", "central_bank"],
    },
    {
        "name": "中国采购与招标网-金融频道",  # 表格 "标探云脑" 无公开入口,改用 chinabidding 第三方聚合
        "url": "https://www.chinabidding.com.cn/bidList-0-0-1-0-0-1.html",  # 金融分类
        "score": 76,
        "keywords": ["bid", "finance", "aggregator"],
    },
    {
        "name": "采招网-金融频道",  # 表格 "银保信" / "中国银联" / "证保信" 垂直机构无公开列表,用 bidcenter 第三方聚合替代
        "url": "https://www.bidcenter.com.cn/bidlist-0-0-0-0-0-0-0-0-0-0-1-1-0.htm",  # 金融分类
        "score": 75,
        "keywords": ["bid", "finance", "aggregator"],
    },
    {
        "name": "晨歌招标网",  # Phase 16 探针: 365bid 跳 lander 失败,改用 chengezhao.com
        "url": "https://www.chengezhao.com/",
        "score": 72,
        "keywords": ["bid", "finance", "aggregator"],
    },
    {
        "name": "招标网-金融频道",  # 第三方聚合
        "url": "https://www.zhaobiao.cn/bidding/list?catId=2",  # 金融分类
        "score": 72,
        "keywords": ["bid", "finance", "aggregator"],
    },
    {
        "name": "采联网-金融频道",  # 第三方聚合
        "url": "https://www.zgzbw.com/list-1.html",  # 金融分类
        "score": 70,
        "keywords": ["bid", "finance", "aggregator"],
    },
    # ===== P1 能源电力（6） =====
    {
        "name": "国家电网电子商务平台",
        "url": "https://ecp.sgcc.com.cn/html/project/index_1.shtml",
        "score": 80,
        "keywords": ["bid", "energy"],
    },
    {
        "name": "南方电网采购",
        "url": "https://www.bidding.csg.cn/",
        "score": 80,
        "keywords": ["bid", "energy"],
    },
    {
        "name": "国家能源采购",
        "url": "https://www.chnenergybidding.com.cn/",
        "score": 78,
        "keywords": ["bid", "energy"],
    },
    {
        "name": "中石化采购",
        "url": "https://www.sinopec-ec.com/",
        "score": 76,
        "keywords": ["bid", "energy"],
    },
    {
        "name": "电力招标网",
        "url": "https://www.dlzb.com/",
        "score": 72,
        "keywords": ["bid", "energy"],
    },
    {
        "name": "电力能源招标网",
        "url": "https://www.dlnyzb.com/",
        "score": 70,
        "keywords": ["bid", "energy"],
    },
    # ===== P1 电信运营商（4） =====
    {
        "name": "中国移动 B2B 采购",
        "url": "https://b2b.10086.cn/",
        "score": 80,
        "keywords": ["bid", "telecom"],
    },
    {
        "name": "中国电信采购",
        "url": "https://caigou.chinatelecom.com.cn/",
        "score": 78,
        "keywords": ["bid", "telecom"],
    },
    {
        "name": "中国联通采购",
        "url": "https://www.chinaunicombidding.com/",
        "score": 76,
        "keywords": ["bid", "telecom"],
    },
    {
        "name": "中国广电采购",
        "url": "https://www.zgdsy.com.cn/",
        "score": 70,
        "keywords": ["bid", "telecom"],
    },
    # ===== P2 医疗教育（2+2=4 源 — Phase 16 补全表格 P2 缺口） =====
    {
        "name": "卫健委采购平台",
        "url": "https://www.nhc.gov.cn/",
        "score": 72,
        "keywords": ["bid", "medical"],
    },
    {
        "name": "教育部政府采购",
        "url": "https://www.moe.gov.cn/",
        "score": 70,
        "keywords": ["bid", "education"],
    },
    # Phase 16 新增 — 表格 "医学院校采购网" / "公立医院采购平台"
    # 两者都没有独立公开列表页,用第三方聚合站的医疗分类替代
    {
        "name": "采招网-医疗频道",  # 表格 "公立医院采购平台"
        "url": "https://www.bidcenter.com.cn/bidlist-0-0-0-0-0-0-0-0-0-0-3-1-0.htm",  # 医疗分类
        "score": 72,
        "keywords": ["bid", "medical", "aggregator"],
    },
    {
        "name": "采招网-教育频道",  # 表格 "医学院校采购网"
        "url": "https://www.bidcenter.com.cn/bidlist-0-0-0-0-0-0-0-0-0-0-4-1-0.htm",  # 教育分类
        "score": 70,
        "keywords": ["bid", "education", "aggregator"],
    },
    # ===== P2 交通制造（4） =====
    {
        "name": "交通运输部采购",
        "url": "https://www.mot.gov.cn/",
        "score": 72,
        "keywords": ["bid", "transport"],
    },
    {
        "name": "国铁集团采购平台",
        "url": "https://www.crgc.cc/",
        "score": 70,
        "keywords": ["bid", "transport"],
    },
    {
        "name": "中车集团采购",
        "url": "https://www.crsc.com.cn/",
        "score": 70,
        "keywords": ["bid", "transport"],
    },
    {
        "name": "中船集团采购",
        "url": "https://www.cssc.com.cn/",
        "score": 70,
        "keywords": ["bid", "transport"],
    },
    # ===== P2 商业聚合（6+6=12 源 — Phase 16 补全表格 P2 缺口） =====
    {
        "name": "采招网",
        "url": "https://www.bidcenter.com.cn/",
        "score": 70,
        "keywords": ["bid", "aggregator"],
    },
    {
        "name": "千里马招标网",
        "url": "https://www.qianlima.com/",
        "score": 68,
        "keywords": ["bid", "aggregator"],
    },
    {
        "name": "乙方宝",
        "url": "https://www.yifangbao.com/",
        "score": 66,
        "keywords": ["bid", "aggregator"],
    },
    {
        "name": "政采云",
        "url": "https://www.zcygov.cn/",
        "score": 72,
        "keywords": ["bid", "aggregator"],
    },
    {
        "name": "军队采购网",
        "url": "https://www.plap.cn/",
        "score": 74,
        "keywords": ["bid", "military"],
    },
    {
        "name": "中招联合招标采购",
        "url": "https://www.zbj.com/",
        "score": 65,
        "keywords": ["bid", "aggregator"],
    },
    # Phase 16 新增 — 补全表格 P2 商业聚合
    {
        "name": "招标网",  # zhaobiao.cn 综合商业聚合
        "url": "https://www.zhaobiao.cn/",
        "score": 68,
        "keywords": ["bid", "aggregator"],
    },
    {
        "name": "比比招标",  # Phase 16 探针发现 365bid 跳 lander 落地页,改用 chengezhao.com
        "url": "https://www.chengezhao.com/zfcg/",  # 政府采购分类
        "score": 67,
        "keywords": ["bid", "aggregator"],
    },
    {
        "name": "采联网",  # zgzbw.com
        "url": "https://www.zgzbw.com/",
        "score": 67,
        "keywords": ["bid", "aggregator"],
    },
    {
        "name": "招标信息港",  # bidnews.cn
        "url": "https://www.bidnews.cn/",
        "score": 66,
        "keywords": ["bid", "aggregator"],
    },
    {
        "name": "易招标",  # ebnew.com
        "url": "https://www.ebnew.com/",
        "score": 65,
        "keywords": ["bid", "aggregator"],
    },
    {
        "name": "深圳公共资源交易",  # szexgrp.com (与 P3 重叠,放这里方便统一)
        "url": "https://www.szexgrp.com/",
        "score": 70,
        "keywords": ["bid", "public", "aggregator"],
    },
    # ===== P3 辅助渠道（2 — 深圳公共资源交易已上移到 P2 商业聚合） =====
    {
        "name": "蚂蚁投标",
        "url": "https://www.mayitb.com/",
        "score": 60,
        "keywords": ["bid", "aggregator"],
    },
    # ===== Phase 19 补全 16 源（HTTP 直连优先, 失败走代理）=====
    # 原 renderer="search" 走 Bing 搜索, 已废弃。改为 HTTP 直连优先,
    # 直连失败时走 ProxySession (127.0.0.1:7897) 代理兜底。
    # ----- P1 金融缺口 -----
    {
        "name": "中国农业发展银行集中采购",
        "url": "https://pms.adbc.com.cn/",
        "score": 78,
        "keywords": ["bid", "finance", "policy_bank"],
    },
    {
        "name": "银保信",
        "url": "https://www.cfxcredit.com/",
        "score": 76,
        "keywords": ["bid", "finance", "banking_assoc"],
    },
    {
        "name": "中国银联采购",
        "url": "https://www.chinaunionpay.com/",
        "score": 76,
        "keywords": ["bid", "finance", "unionpay"],
    },
    {
        "name": "知了标讯",
        "url": "https://www.zhiliaobiaoxun.com/",
        "score": 70,
        "keywords": ["bid", "finance", "aggregator"],
    },
    {
        "name": "证保信",
        "url": "https://zgzx-pa.com.cn/",
        "score": 70,
        "keywords": ["bid", "finance", "cert_registry"],
    },
    # ----- P1 能源电力缺口 -----
    {
        "name": "华能电子商务平台",
        "url": "https://ec.chng.com.cn/",
        "score": 78,
        "keywords": ["bid", "energy", "huaneng"],
    },
    {
        "name": "大唐电子商务平台",
        "url": "https://www.cdt-ec.com/",
        "score": 78,
        "keywords": ["bid", "energy", "datang"],
    },
    {
        "name": "华电电子商务平台",
        "url": "https://www.chdtp.com/",
        "score": 78,
        "keywords": ["bid", "energy", "huadian"],
    },
    {
        "name": "中化商务电子招投标",
        "url": "https://ebid.sinochemitc.com/",
        "score": 74,
        "keywords": ["bid", "energy", "sinochem"],
    },
    {
        "name": "深圳阳光采购平台",
        "url": "https://ygcg.szexgrp.com/",
        "score": 72,
        "keywords": ["bid", "public", "shenzhen"],
    },
    # ----- P2 商业聚合缺口 -----
    {
        "name": "招标采购导航网",
        "url": "https://www.okcis.cn/",
        "score": 68,
        "keywords": ["bid", "aggregator", "okcis"],
    },
    {
        "name": "比地招标网",
        "url": "https://www.bidizhaobiao.com/",
        "score": 66,
        "keywords": ["bid", "aggregator", "bidizhaobiao"],
    },
    {
        "name": "元博招标网",
        "url": "https://www.bidchance.com/",
        "score": 66,
        "keywords": ["bid", "aggregator", "bidchance"],
    },
    {
        "name": "中国国际招标网",
        "url": "https://chinabidding.mofcom.gov.cn/",
        "score": 72,
        "keywords": ["bid", "aggregator", "mofcom"],
    },
    {
        "name": "中国政府采购招标网",
        "url": "https://www.chinabidding.org.cn/",
        "score": 66,
        "keywords": ["bid", "aggregator", "chinabidding_org"],
    },
    # ----- P3 辅助缺口 -----
    {
        "name": "中国外汇交易中心",
        "url": "https://www.chinamoney.com.cn/",
        "score": 68,
        "keywords": ["bid", "finance", "forex"],
    },
]

# 标讯源: HTTP 直连优先, 失败时走 ProxySession (127.0.0.1:7897) 兜底。
# 原 renderer="search" (Bing 搜索) 和 renderer="crawl4ai" 已废弃。
for _src in BID_SOURCES:
    _src.setdefault("renderer", "aiohttp")


# ---------------------------------------------------------------------------
# 四线 AND/OR 关键词体系（已提取到 bid_utils.py）
# 保留 SECURITY_KEYWORDS 等导出符号的引用，供外部模块兼容导入。
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Phase 8: 标讯地区提取 — 从标题中解析省级行政区
# ---------------------------------------------------------------------------
# 覆盖 34 个省级行政区（23 省 + 4 直辖市 + 5 自治区 + 2 特别行政区）
_PROVINCE_PATTERNS: list[tuple[str, str]] = [
    # 省
    ("黑龙江", r"黑龙江(?:省)?"),
    ("吉林", r"吉林(?:省)?"),
    ("辽宁", r"辽宁(?:省)?"),
    ("河北", r"河北(?:省)?"),
    ("山西", r"山西(?:省)?"),
    ("江苏", r"江苏(?:省)?"),
    ("浙江", r"浙江(?:省)?"),
    ("安徽", r"安徽(?:省)?"),
    ("福建", r"福建(?:省)?"),
    ("江西", r"江西(?:省)?"),
    ("山东", r"山东(?:省)?"),
    ("河南", r"河南(?:省)?"),
    ("湖北", r"湖北(?:省)?"),
    ("湖南", r"湖南(?:省)?"),
    ("广东", r"广东(?:省)?"),
    ("海南", r"海南(?:省)?"),
    ("四川", r"四川(?:省)?"),
    ("贵州", r"贵州(?:省)?"),
    ("云南", r"云南(?:省)?"),
    ("陕西", r"陕西(?:省)?"),
    ("甘肃", r"甘肃(?:省)?"),
    ("青海", r"青海(?:省)?"),
    ("台湾", r"台湾(?:省)?"),
    # 直辖市
    ("北京", r"北京(?:市)?"),
    ("天津", r"天津(?:市)?"),
    ("上海", r"上海(?:市)?"),
    ("重庆", r"重庆(?:市)?"),
    # 自治区
    ("内蒙古", r"内蒙古(?:自治区)?"),
    ("广西", r"广西(?:壮族自治区|自治区)?"),
    ("西藏", r"西藏(?:自治区)?"),
    ("宁夏", r"宁夏(?:回族自治区|自治区)?"),
    ("新疆", r"新疆(?:维吾尔自治区|自治区)?"),
    # 特别行政区
    ("香港", r"香港(?:特别行政区)?"),
    ("澳门", r"澳门(?:特别行政区)?"),
]

# 编译好的正则（在 _extract_region 中使用 _PROVINCE_PATTERNS 逐一匹配）


def _extract_region(text: str) -> str | None:
    """从标题/内容中提取省级行政区名称。

    Args:
        text: 标讯标题或摘要

    Returns:
        省级行政区名（如 "北京"、"广东"），或 None

    Example:
        >>> _extract_region("广东省某单位网络安全升级改造项目招标公告")
        '广东'
        >>> _extract_region("北京市公安局视频监控系统采购")
        '北京'
    """
    if not text:
        return None
    for name, pattern in _PROVINCE_PATTERNS:
        if re.search(pattern, text):
            return name
    return None


class BidCollector(BaseCollector):
    """采集招标资讯热点数据。Phase 9 改造：聚焦网络安全/AI安全。

    V1.9 变更: 废弃 renderer="search" (Bing 搜索) 和 renderer="crawl4ai"。
    改为 HTTP 直连优先, 失败时走 ProxySession (127.0.0.1:7897) 代理兜底。
    """

    category = Category.BID
    sources = BID_SOURCES
    timeout = 25
    max_items = 40
    min_items_threshold = 3

    def _is_relevant(self, title: str, summary: str = "") -> bool:
        """判断一条标讯是否网络安全/AI安全相关。

        规则：
        - title 或 summary 任一命中四线关键词集合 → 保留
        - 否则过滤掉（避免大量无关采购信息）
        """
        return is_security_bid(title) or is_security_bid(summary)

    async def _fetch_with_fallback(
        self, source: dict
    ) -> tuple[list[HotspotItem], Any]:
        """Playwright (Crawl4ai) 优先, 失败走 HTTP 直连 + 代理兜底。

        标讯网站普遍有强反爬措施 (JS 渲染 / 验证码 / User-Agent 检测),
        Playwright 模拟真实浏览器能绕过大部分反爬。
        1. Crawl4ai (Playwright) — 模拟正常用户
        2. 失败 → aiohttp 直连 (无代理)
        3. 直连失败 → ProxySession (127.0.0.1:7897)
        4. 全失败 → 返回 SourceResult(error)
        """
        from datetime import datetime
        from datetime import timezone as _tz

        import aiohttp

        from backend.domain.collection import SourceResult

        start = datetime.now(_tz.utc)
        source_name = source.get("name", "unknown")
        source_url = source["url"]
        headers = {"User-Agent": _UA}
        html: str | None = None
        used_proxy = False
        used_crawl4ai = False

        # ---- 第 1 步: Crawl4ai (Playwright) 模拟正常用户 ----
        # 标讯网站需要 JS 渲染 + 真实浏览器指纹绕过反爬
        crawl4ai_result = await self._fetch_with_crawl4ai(source_url)
        if crawl4ai_result.success and crawl4ai_result.content:
            used_crawl4ai = True
            html = crawl4ai_result.content
            self.logger.debug(f"bid crawl4ai OK {source_name!r}")

        # ---- 第 2 步: Crawl4ai 失败, 走 aiohttp 直连 ----
        if html is None:
            try:
                timeout_obj = aiohttp.ClientTimeout(total=self.timeout)
                async with aiohttp.ClientSession(timeout=timeout_obj) as session:
                    async with session.get(source_url, headers=headers, ssl=False) as resp:
                        if resp.status == 200:
                            html = await resp.text()
                        else:
                            self.logger.debug(
                                f"bid direct {source_name!r} HTTP {resp.status}"
                            )
                if html:
                    self.logger.debug(f"bid direct OK {source_name!r}")
            except Exception as e:
                self.logger.debug(
                    f"bid direct failed {source_name!r}: "
                    f"{type(e).__name__}: {str(e)[:60]}"
                )
                html = None

        # ---- 第 3 步: 直连也失败, 对需要代理的源走代理兜底 ----
        if html is None:
            try:
                from backend.proxy_config import should_use_proxy
                if not should_use_proxy(source_url):
                    self.logger.debug(
                        f"bid proxy skipped {source_name!r} (no proxy needed)"
                    )
                else:
                    from backend.proxy_session import ProxySession
                    timeout_obj = aiohttp.ClientTimeout(total=self.timeout)
                    async with ProxySession(headers=headers, timeout=timeout_obj) as session:
                        async with session.get(source_url, ssl=False) as resp:
                            if resp.status == 200:
                                html = await resp.text()
                                used_proxy = True
                            else:
                                self.logger.debug(
                                    f"bid proxy {source_name!r} HTTP {resp.status}"
                                )
                    if html:
                        self.logger.debug(f"bid proxy OK {source_name!r}")
            except Exception as e:
                self.logger.warning(
                    f"bid proxy failed {source_name!r}: "
                    f"{type(e).__name__}: {str(e)[:60]}"
                )

        # ---- 全失败 ----
        if html is None:
            duration = int(
                (datetime.now(_tz.utc) - start).total_seconds() * 1000
            )
            return [], SourceResult(
                source_name=source_name,
                source_url=source_url,
                item_count=0,
                error_msg="crawl4ai+direct+proxy all failed",
                duration_ms=duration,
            )

        # ---- 解析 ----
        try:
            raw_items = self._parse_html(html, source)
            items = self._build_items(raw_items, source)
        except Exception as e:
            duration = int(
                (datetime.now(_tz.utc) - start).total_seconds() * 1000
            )
            self.logger.warning(
                f"bid parse failed {source_name!r} "
                f"(crawler={'crawl4ai' if used_crawl4ai else 'aiohttp'}): "
                f"{type(e).__name__}: {str(e)[:50]}"
            )
            return [], SourceResult(
                source_name=source_name,
                source_url=source_url,
                item_count=0,
                error_msg=f"parse_error: {type(e).__name__}: {str(e)[:100]}",
                duration_ms=duration,
            )

        # Phase 8: 从标题提取地区
        for it in items:
            if isinstance(it, dict):
                region = _extract_region(it.get("title", ""))
                if region:
                    it["region"] = region

        duration = int(
            (datetime.now(_tz.utc) - start).total_seconds() * 1000
        )
        return items, SourceResult(
            source_name=source_name,
            source_url=source_url,
            item_count=len(items),
            duration_ms=duration,
        )

    def _parse_html(self, html: str, source: dict) -> list[dict]:
        """解析招标页面 HTML，过滤无关采购信息。

        Phase 9 增强：
        1. 优先从招标页面常见结构中提取 title + url
        2. 关键词过滤：只保留网络安全/AI安全相关条目
        """
        raw_items = super()._parse_html(html, source)
        out: list[dict] = []
        seen: set[str] = set()
        for it in raw_items:
            title = it.get("title", "") or ""
            summary = it.get("summary", "") or ""
            if not self._is_relevant(title, summary):
                continue
            url = it.get("url", "") or ""
            if url in seen:
                continue
            seen.add(url)
            out.append(it)
            if len(out) >= self.max_items:
                break
        return out

    def _build_items(
        self, raw_items: list[dict[str, Any]], source: dict
    ) -> list[HotspotItem]:
        """Bid 专用 _build_items：published_at 兜底 + 关键词过滤。

        2026-08-10 (P0 RCA 修复后暴露的第二道门禁):
        Bid 列表页既无 ``<meta property="article:published_time">``
        也无 URL slug 日期,``_extract_published_at`` 返回 None,
        ``_build_items`` 上游第 102 行 ``if published_at is None: continue``
        把全部真实标讯全部杀死。

        修复: 在 published_at is None 时, 注入 ``fetched_at`` 作为
        ``published_at`` 兜底 (同 :mod:`telegram_collector` 模式)。
        同时保留 Phase 47 时效硬门禁 (早于本周一仍拒收)。
        """
        from backend.domain.enums import Category as _Cat
        from backend.utils.business_days import current_week_start

        _extract_bid_status = None
        if self.category == _Cat.BID:
            from backend.collectors.bid_status import extract_bid_status
            _extract_bid_status = extract_bid_status

        _NAV_CTA = re.compile(
            r"查看更多|更多\s*>>|更多\s*>|立即查看|立即申请|"
            r"立即报名|马上了解|点击查看|>>>|>>>\s*$|>>\s*$|"
            r"入驻\s*\S{0,4}$|注册\s*\S{0,4}$|"
            r"查看全部|点击进入|关注我们|关于我们|"
            r"^\s*[Aa][Bb][Oo][Uu][Tt]\s*$|"
            r"^\s*[Cc][Oo][Nn][Tt][Aa][Cc][Tt]\s*$|"
            r"^更多$|^首页$|^登录$|^注册$"
        )
        _MIN_TITLE_LEN = 8
        _MAX_TITLE_LEN = 200

        now = datetime.now(timezone.utc)
        items: list[HotspotItem] = []
        skipped = 0
        recency_threshold = current_week_start()
        for i, raw in enumerate(raw_items[: self.max_items * 2]):
            title = (raw.get("title") or "").strip()
            url = (raw.get("url") or "").strip()
            if not title or len(title) < _MIN_TITLE_LEN:
                skipped += 1
                continue
            if len(title) > _MAX_TITLE_LEN:
                skipped += 1
                continue
            if _NAV_CTA.search(title):
                skipped += 1
                continue
            if not self._title_relevant(title, url, source):
                skipped += 1
                continue

            # published_at 兜底: bid 列表页普遍无 meta/JSON-LD/slug 日期,
            # 用 fetch time 兜底 (同 telegram_collector)
            published_at = raw.get("published_at")
            if published_at is None:
                published_at = now
                # 标记: 让 quality gate 知道这是兜底时间
                raw["_published_at_fallback"] = True

            if not isinstance(published_at, datetime) or published_at.tzinfo is None:
                skipped += 1
                continue
            if published_at < recency_threshold:
                skipped += 1
                continue

            bid_status_val = None
            if _extract_bid_status is not None:
                bid_status_val = _extract_bid_status(
                    title, raw.get("summary", "") or "",
                )
            try:
                item_id = raw.get("id") or f"{self.name}_{source['name']}_{i}"
                item = HotspotItem(
                    id=item_id,
                    title=title[:500],
                    summary=(raw.get("summary") or "")[:500] or None,
                    source=source["name"][:50],
                    url=raw["url"],
                    category=self.category,
                    published_at=published_at,
                    fetched_at=now,
                    ingested_at=now,
                    bid_status=bid_status_val,
                    region=raw.get("region"),
                    score=source.get("score", 75),
                    is_fallback=False,
                    quality_score=100,
                    quality_flags=[],
                    url_check_status="pending",
                )
                # 若兜底, 在 quality_flags 记录 (审计可追溯)
                if raw.get("_published_at_fallback"):
                    item.quality_flags.append("published_at_from_fetch_time")
                items.append(item)
                if len(items) >= self.max_items:
                    break
            except Exception as e:
                self.logger.warning(
                    f"skip item {i}: {type(e).__name__}: {str(e)[:50]}"
                )
        if skipped:
            self.logger.debug(
                f"{source['name']} filtered {skipped} "
                f"nav/cta/short/irrelevant/no-pub/historical titles"
            )
        return items

    async def fetch_source(self, source: dict):
        """HTTP 直连优先, 失败走代理兜底。

        - 全部源走 :meth:`_fetch_with_fallback` (直连→代理)
        - 废弃 renderer="search" (Bing 搜索) 和 renderer="crawl4ai"
        """
        return await self._fetch_with_fallback(source)

    async def _fetch_with_crawl4ai(self, url: str) -> CrawlResult:
        """Phase 16: Crawl4ai fallback for government procurement sites with strong anti-crawling."""
        try:
            from backend.parsers.crawl4ai_parser import Crawl4aiParser
            parser = Crawl4aiParser()
            return await parser.crawl(url)
        except ImportError:
            return CrawlResult(url=url, success=False, error="Crawl4aiParser not available")
        except Exception as e:
            self.logger.warning(f"crawl4ai fallback failed: {e}")
            return CrawlResult(url=url, success=False, error=str(e))


__all__ = [
    "BID_SOURCES",
    "PROCUREMENT_KEYWORDS",
    "SECURITY_KEYWORDS",
    "SECURITY_KEYWORD_SET",
    "BidCollector",
    "is_security_bid",
]
