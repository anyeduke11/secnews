"""标讯状态字段提取 (Phase 20)。

从标讯标题/摘要中按关键词正则识别标讯的当前状态,落库到 ``HotspotItem.bid_status``。

状态优先级(从高到低,先匹配者胜出)
-----------------------------------
1. **变更**     — 标题含 "变更公告" / "更正公告" / "澄清公告" / "修改通知"
2. **终止**     — 标题含 "终止公告" / "废标公告" / "流标公告" / "失败公告"
3. **中标**     — 标题含 "中标公告" / "中标候选人" / "中标公示" / "成交候选人"
4. **成交**     — 标题含 "成交公告" / "结果公告" / "中标结果" (注意区分"中标公告")
5. **询价**     — 标题含 "询比" / "询价" / "竞争性谈判" / "磋商公告" / "磋商"
6. **比选**     — 标题含 "比选" / "竞价" / "竞谈"
7. **招标中**   — 标题含 "招标公告" / "公开招标" / "投标邀请" / "采购公告"
                    (默认兜底)

设计要点
--------
- 关键词检查用 ``in`` 子串匹配,中文标讯标题字符短,O(n*m) 可接受
- 优先级: 同一标题出现多个状态词,按上面顺序识别(变更 > 终止 > 中标 > ...)
  例: "X 项目招标公告(更正)" → 识别为 "变更" 而非 "招标中"
- 不识别的标题返回 ``"其他"``,入库时落 ``"其他"`` 即可,不阻断

使用
----
>>> from backend.collectors.bid_status import extract_bid_status
>>> extract_bid_status("X 项目招标公告")
'招标中'
>>> extract_bid_status("X 项目中标候选人公示")
'中标'
>>> extract_bid_status("X 项目变更公告")
'变更'
>>> extract_bid_status("X 项目")
'其他'
"""
from __future__ import annotations

import re
from typing import Final


# 状态 → 关键词列表
# 顺序敏感: 上面状态优先级高,先命中先用
_STATUS_RULES: Final[list[tuple[str, tuple[str, ...]]]] = [
    (
        "变更",
        (
            "变更公告", "更正公告", "澄清公告", "修改通知",
            "变更通知", "更正通知", "变更", "更正", "澄清",
        ),
    ),
    (
        "终止",
        (
            "终止公告", "废标公告", "流标公告", "失败公告",
            "终止通知", "废标", "流标", "终止",
        ),
    ),
    (
        "中标",
        (
            "中标候选人", "中标公示", "中标公告", "中标结果公告",
            "中标结果公示", "中标通知", "定标公告", "预中标",
        ),
    ),
    (
        "成交",
        (
            "成交公告", "成交结果", "成交候选人", "结果公告",
            "中标结果",  # 兜底放这里(比"中标公告"更具体)
        ),
    ),
    (
        "询价",
        (
            "询比公告", "询价公告", "竞争性谈判", "竞争性磋商",
            "磋商公告", "磋商", "询比", "询价",
        ),
    ),
    (
        "比选",
        (
            "比选公告", "竞价公告", "竞谈公告",
            "比选", "竞价", "竞谈",
        ),
    ),
    (
        "招标中",
        (
            "招标公告", "公开招标", "邀请招标", "投标邀请",
            "采购公告", "采购项目公告", "招标",
        ),
    ),
]


def extract_bid_status(title: str, summary: str = "") -> str:
    """从标讯标题/摘要识别状态。

    Parameters
    ----------
    title: 标讯标题(必填)
    summary: 标讯摘要(可选,作为补充识别)

    Returns
    -------
    状态字符串,见模块顶部优先级表。未识别 → ``"其他"``。
    """
    if not title:
        return "其他"
    text = (title or "") + " " + (summary or "")

    # 优先在 title 中识别,再在 title+summary 中兜底
    for status, keywords in _STATUS_RULES:
        for kw in keywords:
            if kw in title:
                return status

    # 兜底:从 title+summary 识别
    for status, keywords in _STATUS_RULES:
        for kw in keywords:
            if kw in text:
                return status

    return "其他"


# 前端 Badge 颜色映射(供前端组件参考,Python 端不直接用)
STATUS_COLOR_MAP: Final[dict[str, str]] = {
    "招标中": "primary",      # 蓝色 — 还在招
    "中标":   "success",      # 绿色 — 已定标
    "成交":   "success",      # 绿色
    "变更":   "warning",      # 黄色 — 注意
    "终止":   "danger",       # 红色 — 已废
    "询价":   "info",         # 浅蓝
    "比选":   "info",         # 浅蓝
    "其他":   "default",      # 灰色
}


__all__ = ["extract_bid_status", "STATUS_COLOR_MAP"]
