"""标讯结构化字段提取 — 从标题/URL 中提取 bid_details 所需字段。

设计动机
--------
Phase 1.3 (Crawler v2): 从列表页解析结果中提取结构化标讯字段，
为 bid_details 表提供数据。提取优先级（§3.5.1）:
  DOM 选择器 > 正则表达式 > LLM 兜底

当前实现: 正则表达式提取（Phase 1 阶段，无需 LLM）。
字段提取均为尽力而为，提取失败时对应字段为空字符串。

字段说明
--------
- bid_no:     项目编号/采购编号，如 "GC-HGX230456"
- buyer:      采购人/招标单位，如 "国家税务总局"
- region:     地区，如 "北京市"、"广东省"
- budget:     预算金额，如 "120万元"
- deadline:   截止时间，如 "2024-06-30"
- bid_status: 标讯状态，如 "招标中"、"中标"
- industry:   行业分类，如 "金融"、"能源"
"""
from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# 正则模式
# ---------------------------------------------------------------------------

# 项目编号 —— 多种格式
_BID_NO_RE = re.compile(
    r"(?:项目|采购|招标|公告)?(?:编号|文号|项目编号|采购编号|招标编号)\s*[：:]\s*(?P<no>\S+)"
)

# 采购人/招标单位 —— 常见于标题开头
_BUYER_RE = re.compile(
    r"(?P<buyer>[\u4e00-\u9fff（）()]{2,30}(?:局|部|委|办|中心|公司|集团|银行|学校|医院|院))"
    r"(?:20\d{2}|202[4-9])?年?(?:采购|招标|竞争性|公开|单一|询价|比选)"
)

# 地区 —— 省级/市级
_REGION_RE = re.compile(
    r"(?P<region>(?:北京|天津|上海|重庆|河北|山西|辽宁|吉林|黑龙江|"
    r"江苏|浙江|安徽|福建|江西|山东|河南|湖北|湖南|广东|广西|海南|"
    r"四川|贵州|云南|西藏|陕西|甘肃|青海|宁夏|新疆|内蒙古|"
    r"台北|香港|澳门)"
    r"(?:省|市|自治区|特别行政区)?)"
)

# 预算金额 —— 数字 + 万元/元/亿
_BUDGET_RE = re.compile(
    r"(?P<budget>预算[：:]\s*[0-9,，.]+[万亿千百]?元|"
    r"[0-9,，.]+[万亿千百]?元\s*(?:人民币|预算)?)"
)

# 截止时间 —— 2024-06-30 格式
_DEADLINE_RE = re.compile(
    r"(?:截止|提交|开标|递交)(?:时间|日期|止)[：:]\s*(?P<date>\d{4}[-/年]\d{1,2}[-/月]\d{1,2})"
)

# 标讯状态 —— 从标题关键词推断
_BID_STATUS_RE = re.compile(
    r"(?P<status>中标|成交|招标|流标|废标|终止|暂停|变更|更正|补充|询价|比选|竞争性磋商|"
    r"竞争性谈判|单一来源|公开招标|邀请招标)"
)

# 行业分类 —— 从标题关键词推断
_INDUSTRY_RE = re.compile(
    r"(?P<industry>金融|银行|证券|保险|能源|电力|电网|石化|电信|运营商|通信|"
    r"医疗|医院|卫生|教育|高校|学校|交通|物流|铁路|"
    r"政府|公安|税务|海关|消防|应急|环保|水利)"
)


def extract_bid_no(title: str) -> str:
    """提取项目编号。"""
    m = _BID_NO_RE.search(title)
    if m:
        return m.group("no").strip().rstrip("）)】」")
    return ""


def extract_buyer(title: str) -> str:
    """提取采购人/招标单位。"""
    m = _BUYER_RE.search(title)
    if m:
        return m.group("buyer").strip()
    return ""


def extract_region(title: str) -> str:
    """提取地区。"""
    m = _REGION_RE.search(title)
    if m:
        return m.group("region").strip()
    return ""


def extract_budget(title: str) -> str:
    """提取预算金额。"""
    m = _BUDGET_RE.search(title)
    if m:
        return m.group("budget").strip()
    return ""


def extract_deadline(title: str) -> Optional[str]:
    """提取截止时间，返回 ISO 日期字符串或 None。"""
    m = _DEADLINE_RE.search(title)
    if m:
        date_str = m.group("date").strip()
        date_str = date_str.replace("年", "-").replace("月", "-").replace("/", "-")
        return date_str
    return None


def extract_bid_status(title: str) -> str:
    """提取标讯状态。"""
    m = _BID_STATUS_RE.search(title)
    if m:
        return m.group("status").strip()
    return ""


def extract_industry(title: str) -> str:
    """提取行业分类。"""
    m = _INDUSTRY_RE.search(title)
    if m:
        return m.group("industry").strip()
    return ""


def extract_all(title: str, url: str = "") -> dict:
    """从标题提取所有结构化字段。

    Args:
        title: 标讯标题
        url: 可选，URL 可能包含额外信息

    Returns:
        dict 包含 bid_no, buyer, region, budget, deadline, bid_status, industry
    """
    return {
        "bid_no": extract_bid_no(title),
        "buyer": extract_buyer(title),
        "region": extract_region(title),
        "budget": extract_budget(title),
        "deadline": extract_deadline(title),
        "bid_status": extract_bid_status(title),
        "industry": extract_industry(title),
    }


__all__ = [
    "extract_all",
    "extract_bid_no",
    "extract_buyer",
    "extract_region",
    "extract_budget",
    "extract_deadline",
    "extract_bid_status",
    "extract_industry",
]