"""Phase 9 资讯作者核实：domain → canonical publisher 注册表

设计目标
--------
对热点资讯，``source`` 字段的"作者"标签必须与 URL 的实际发布者匹配。
例如：URL 指向 ``msrc.microsoft.com`` 时显示 "KrebsOnSecurity" 是错误
的（哪怕 RSS feed 里这样写），应该纠正为 ``MSRC``。

实现
----
1. ``PUBLISHER_REGISTRY``: 已知发布者的 domain 后缀 → canonical name 映射
2. ``resolve_publisher(url, claimed)`` 主入口：
   - 从 URL 提取 registered/etld+1 domain
   - 在 registry 中查匹配（最长后缀优先）
   - 返回 ``(canonical, is_match, reason)``，让 gate 据此降权/纠正

后续可扩展
----------
- 读取 settings 表 ``quality.author_override``（运维手动 override）
- 自动从 RSS feed 拉 publisher 描述 (channel.author / dc.creator)
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# 已知发布者注册表（domain suffix -> canonical name）
#
# 排序：长 suffix 优先（更具体匹配）
# ---------------------------------------------------------------------------
PUBLISHER_REGISTRY: list[tuple[str, str]] = [
    # 微软相关
    ("msrc.microsoft.com", "MSRC (Microsoft Security Response Center)"),
    ("learn.microsoft.com", "Microsoft Learn"),
    ("support.microsoft.com", "Microsoft Support"),
    ("blogs.microsoft.com", "Microsoft Blog"),
    ("msrc-blog.microsoft.com", "MSRC Blog"),
    # Apple
    ("support.apple.com", "Apple Security"),
    ("developer.apple.com", "Apple Developer"),
    ("security.apple.com", "Apple Security"),
    # Google
    ("googleprojectzero.blogspot.com", "Google Project Zero"),
    ("chromereleases.googleblog.com", "Google Chrome Releases"),
    ("security.googleblog.com", "Google Security Blog"),
    ("blog.google", "Google Blog"),
    # 主流网安媒体
    ("krebsonsecurity.com", "KrebsOnSecurity"),
    ("thehackernews.com", "The Hacker News"),
    ("bleepingcomputer.com", "BleepingComputer"),
    ("therecord.media", "The Record"),
    ("darkreading.com", "Dark Reading"),
    ("threatpost.com", "Threatpost"),
    ("securityweek.com", "SecurityWeek"),
    ("securityaffairs.com", "Security Affairs"),
    ("cybernews.com", "Cybernews"),
    ("theregister.com", "The Register"),
    # 行业组织 / CERT
    ("cert.org", "CERT/CC"),
    ("cisa.gov", "CISA"),
    ("nvd.nist.gov", "NIST NVD"),
    ("cve.mitre.org", "MITRE CVE"),
    ("us-cert.cisa.gov", "US-CERT"),
    ("schneier.com", "Schneier on Security"),
    # 中文网安媒体
    ("freebuf.com", "FreeBuf"),
    ("anquanke.com", "安全客"),
    # Phase 22: SecWiki (secnews §三 RSS 5 源补齐)
    ("sec-wiki.com", "SecWiki"),
    ("4hou.com", "嘶吼"),
    ("seebug.org", "Seebug"),
    ("knownsec.com", "知道创宇"),
    ("360.net", "360"),
    ("dbappsecurity.com.cn", "绿盟科技"),
    # Phase 23: venustech 报 403, 改用 secnews §三 RSS 源 (gm7.org = 启明星辰安全简讯)
    ("venustech.com.cn", "启明星辰"),  # 保留兼容 — 旧条目 author 还在这域名
    ("gm7.org", "启明星辰"),
    # 金融/政府/科技
    ("sec.gov", "SEC EDGAR"),
    ("reuters.com", "Reuters"),
    ("bloomberg.com", "Bloomberg"),
    ("wsj.com", "Wall Street Journal"),
    ("ft.com", "Financial Times"),
    # GitHub / 开源
    ("github.com", "GitHub"),
    ("github.blog", "GitHub Blog"),
    # 招标
    ("ccgp.gov.cn", "中国政府采购网"),
    ("ggzy.gov.cn", "全国公共资源交易平台"),
    ("zycg.gov.cn", "中央政府采购网"),
    # Phase 21 扩充: 资讯类高频域名 (避免 author_unknown, 保持抓取源=真实发布者)
    # 业界网络安全/科技媒体 — 抓取源名 = 真实发布者,严格匹配
    # 注: 已有 thehackernews.com / schneier.com / knownsec.com 在上面,
    #     不重复添加;这里只补缺的域名
    ("huxiu.com", "虎嗅"),
    ("itjuzi.com", "IT桔子"),
    ("hackernews.com", "HackerNews"),
    ("secrss.com", "安全内参"),
    ("easyaq.com", "E安全"),
    ("hackread.com", "HackRead"),
    ("djbh.net", "等级保护网"),
    ("tc260.org.cn", "TC260 信安标委"),
    ("cnnvd.org.cn", "CNNVD 国家漏洞库"),
    ("nfra.gov.cn", "国家金融监督管理总局"),
    ("csrc.gov.cn", "中国证监会"),
    ("pbc.gov.cn", "中国人民银行"),
    ("ti.qianxin.com", "奇安信威胁情报"),
    ("sangfor.com.cn", "深信服科技"),
    ("nsfocus.com", "绿盟科技"),
    # Bid sources — Phase 19/21 扩到 registry,保证 author=真实发布者
    ("bidcenter.com.cn", "采招网"),
    ("chengezhao.com", "晨歌招标网"),
    ("qianlima.com", "千里马招标网"),
    ("zcygov.cn", "政采云"),
    ("plap.cn", "军队采购网"),
    ("zhaobiao.cn", "招标网"),
    ("zgzbw.com", "采联网"),
    ("dlzb.com", "电力招标网"),
    ("dlnyzb.com", "电力能源招标网"),
    ("yifangbao.com", "乙方宝"),
    ("b2b.10086.cn", "中国移动 B2B 采购"),
    ("caigou.chinatelecom.com.cn", "中国电信采购"),
    ("chinaunicombidding.com", "中国联通采购"),
    ("nhc.gov.cn", "卫健委采购平台"),
    ("moe.gov.cn", "教育部政府采购"),
    ("mot.gov.cn", "交通运输部采购"),
    ("crgc.cc", "国铁集团采购平台"),
    ("ecp.sgcc.com.cn", "国家电网电子商务平台"),
    ("bidding.csg.cn", "南方电网采购"),
    ("chnenergybidding.com.cn", "国家能源采购"),
    ("sinopec-ec.com", "中石化采购"),
    ("szexgrp.com", "深圳公共资源交易"),
    # Phase 19 扩充: v1.6.3 新增 16 标讯信源 (renderer=search 路径)
    ("pms.adbc.com.cn", "中国农业发展银行集中采购"),
    ("cfxcredit.com", "银保信"),
    ("chinaunionpay.com", "中国银联"),
    ("zhiliaobiaoxun.com", "知了标讯"),
    ("zgzx-pa.com.cn", "证保信"),
    ("ec.chng.com.cn", "华能电子商务平台"),
    ("cdt-ec.com", "大唐电子商务平台"),
    ("chdtp.com", "华电电子商务平台"),
    ("ebid.sinochemitc.com", "中化商务电子招投标"),
    ("ygcg.szexgrp.com", "深圳阳光采购平台"),
    ("okcis.cn", "招标采购导航网"),
    ("bidizhaobiao.com", "比地招标网"),
    ("bidchance.com", "元博招标网"),
    ("chinabidding.mofcom.gov.cn", "中国国际招标网"),
    ("chinabidding.org.cn", "中国政府采购招标网"),
    ("chinamoney.com.cn", "中国外汇交易中心"),
    # Phase 14 扩充: 资讯类高频域名 (降低 AuthorVerification unknown 比例)
    ("36kr.com", "36氪"),
    ("jiqizhixin.com", "机器之心"),
    ("qbitai.com", "量子位"),
    ("sina.com.cn", "新浪财经"),
    ("finance.sina.com.cn", "新浪财经"),
    ("eastmoney.com", "东方财富"),
    ("wallstreetcn.com", "华尔街见闻"),
    ("xueqiu.com", "雪球"),
    ("caixin.com", "财新网"),
    ("pedaily.cn", "投资界"),
    ("news.ycombinator.com", "HackerNews"),
    ("ycombinator.com", "Y Combinator"),
    ("trending.ycombinator.com", "HackerNews"),
    # Phase 26: AIhot / 小互AI 解读站 (RSS/JSON 接入)
    ("aihot.virxact.com", "AIhot"),
    ("best.xiaohu.ai", "小互AI"),
    ("xiaohu.ai", "小互AI"),
    # Phase 29: tophub.today 聚合站 (GitHub 热榜分类页)
    ("tophub.today", "TopHub GitHub 热榜"),
]


# 别名 / 缩写 → canonical name（用于不匹配时尝试匹配 claimed）
ALIASES: dict[str, str] = {
    "msrc": "MSRC (Microsoft Security Response Center)",
    "microsoft": "MSRC (Microsoft Security Response Center)",
    "microsoft security": "MSRC (Microsoft Security Response Center)",
    "msft": "MSRC (Microsoft Security Response Center)",
    "apple": "Apple Security",
    "google": "Google Security Blog",
    "project zero": "Google Project Zero",
    "cisa": "CISA",
    "cert": "CERT/CC",
    "cert/cc": "CERT/CC",
    "nist": "NIST NVD",
    "mitre": "MITRE CVE",
    "seebug": "Seebug",
    "freebuf": "FreeBuf",
    "安全客": "安全客",
    # 嘶吼修正: 4hou.com 的真实发布者是"嘶吼", "四哥"是栏目名/作者名
    "嘶吼": "嘶吼",
    "4hou": "嘶吼",
    "四哥": "嘶吼",  # 别名映射(修正历史错误)
    "知道创宇": "知道创宇",
    "绿盟": "绿盟科技",
    "启明星辰": "启明星辰",
    "krebsonsecurity": "KrebsOnSecurity",
    "the hacker news": "The Hacker News",
    "bleepingcomputer": "BleepingComputer",
    "schneier": "Schneier on Security",
    # Phase 14 扩充: 资讯类 source 名 → canonical
    "36氪": "36氪",
    "36kr": "36氪",
    "36氪ai": "36氪",
    "机器之心": "机器之心",
    "量子位": "量子位",
    "新浪财经": "新浪财经",
    "东方财富": "东方财富",
    "华尔街见闻": "华尔街见闻",
    "雪球": "雪球",
    "财新网": "财新网",
    "投资界": "投资界",
    "hackernews": "HackerNews",
    "hacker news": "HackerNews",
    # Phase 19 扩充: v1.6.3 新增 16 标讯信源别名
    "中国农业发展银行": "中国农业发展银行集中采购",
    "农发行": "中国农业发展银行集中采购",
    "银保信": "银保信",
    "中国银联": "中国银联",
    "知了标讯": "知了标讯",
    "证保信": "证保信",
    "华能": "华能电子商务平台",
    "大唐": "大唐电子商务平台",
    "华电": "华电电子商务平台",
    "中化": "中化商务电子招投标",
    "深圳阳光": "深圳阳光采购平台",
    "okcis": "招标采购导航网",
    "比地": "比地招标网",
    "元博": "元博招标网",
    "mofcom": "中国国际招标网",
    "chinabidding_org": "中国政府采购招标网",
    "外汇交易中心": "中国外汇交易中心",
    # Phase 29: TopHub 聚合站别名
    "tophub": "TopHub GitHub 热榜",
    "tophub github 热榜": "TopHub GitHub 热榜",
    "tophub github": "TopHub GitHub 热榜",
}


def _extract_registered_domain(url: str) -> Optional[str]:
    """从 URL 提取 host（含子域），不做 PSL 解析但足够用。"""
    if not url:
        return None
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        host = parsed.hostname or ""
        host = host.lower().strip()
        if host.startswith("www."):
            host = host[4:]
        return host or None
    except Exception:
        return None


def _find_matching_suffix(host: str) -> Optional[str]:
    """在 PUBLISHER_REGISTRY 中查 host 命中的最长 suffix。

    Parameters
    ----------
    host: 已去除 ``www.`` 的小写主机名。
    """
    if not host:
        return None
    # 优先完全匹配
    for suffix, name in PUBLISHER_REGISTRY:
        if host == suffix:
            return name
    # 后缀匹配（最长优先 → 列表已按长→短排序）
    for suffix, name in PUBLISHER_REGISTRY:
        if host.endswith("." + suffix):
            return name
    return None


def resolve_publisher(
    url: str, claimed: Optional[str] = None
) -> tuple[Optional[str], bool, str]:
    """根据 URL 域名反推真实发布者。

    Parameters
    ----------
    url: 资讯 URL。
    claimed: 现有 ``source`` 字段值（可能是错误标签）。

    Returns
    -------
    ``(canonical, is_match, reason)``:
    - ``canonical``: 注册表里查到的标准发布者名（可能 None）
    - ``is_match``: claimed 与 canonical 匹配（含 alias）时 True
    - ``reason``: 文本原因（"url_match" / "url_known" / "url_unknown" 等）

    Examples
    --------
    >>> resolve_publisher(
    ...     "https://msrc.microsoft.com/update-guide/.../CVE-2026-50507",
    ...     "KrebsOnSecurity",
    ... )
    ('MSRC (Microsoft Security Response Center)', False,
     "url_domain=msrc.microsoft.com -> MSRC; claimed='KrebsOnSecurity' mismatch")

    >>> resolve_publisher(
    ...     "https://krebsonsecurity.com/2026/06/foo/",
    ...     "KrebsOnSecurity",
    ... )
    ('KrebsOnSecurity', True, "url_domain=krebsonsecurity.com match claimed")
    """
    host = _extract_registered_domain(url)
    if not host:
        return None, False, "url_invalid"

    canonical = _find_matching_suffix(host)
    if canonical is None:
        # URL 域名不在注册表里
        if claimed:
            return None, False, f"url_unknown domain={host}"
        return None, False, f"url_unknown domain={host}"

    # 在注册表里
    if not claimed:
        return canonical, False, f"url_known domain={host} -> {canonical}"

    # 标准化 claimed 做比较
    norm_claimed = _normalize_name(claimed)
    norm_canon = _normalize_name(canonical)
    if norm_claimed == norm_canon:
        return canonical, True, f"url_match domain={host} == {canonical}"

    # 尝试 alias 匹配
    aliased = ALIASES.get(norm_claimed)
    if aliased and _normalize_name(aliased) == norm_canon:
        return canonical, True, f"alias_match claimed={claimed} -> {canonical}"

    return (
        canonical,
        False,
        f"url_mismatch domain={host} -> {canonical}; claimed='{claimed}'",
    )


def _normalize_name(name: str) -> str:
    """去除括号内容、标点、空白 → 小写，用于比较。"""
    if not name:
        return ""
    out = name.lower()
    # 去掉括号内容
    if "(" in out:
        out = out.split("(", 1)[0]
    if "（" in out:
        out = out.split("（", 1)[0]
    # 保留字母数字中文
    keep = []
    for ch in out:
        if ch.isalnum() or "\u4e00" <= ch <= "\u9fff":
            keep.append(ch)
    return "".join(keep).strip()


__all__ = [
    "PUBLISHER_REGISTRY",
    "ALIASES",
    "resolve_publisher",
    "_extract_registered_domain",
    "_find_matching_suffix",
    "_normalize_name",
]
