"""独立解析器模块 — 按站点隔离 HTML/JSON/JS 解析逻辑。

Phase 1 (v1.3.0): 从 BaseCollector 中提取站点特定解析逻辑，
使解析器可独立测试和版本化。

用法
----
from backend.parsers import get_parser
parser = get_parser(source_id)
items = parser.parse(content, url, content_type)
"""
from __future__ import annotations

from typing import Optional

from backend.parsers.base_parser import BaseSourceParser, RawItem

# 解析器注册表
_PARSER_REGISTRY: dict[str, type[BaseSourceParser]] = {}


def register_parser(source_id: str, parser_cls: type[BaseSourceParser]) -> None:
    """注册一个解析器到全局注册表。"""
    _PARSER_REGISTRY[source_id] = parser_cls


def get_parser(source_id: str) -> BaseSourceParser | None:
    """获取指定 source_id 的解析器实例。"""
    cls = _PARSER_REGISTRY.get(source_id)
    if cls is None:
        return None
    return cls()


def list_parsers() -> list[str]:
    """列出所有已注册的解析器 ID。"""
    return list(_PARSER_REGISTRY.keys())


# 自动注册内置解析器
def _register_builtin() -> None:
    from backend.parsers.aihot_parser import AihotParser, SOURCE_ID as AHIOT_ID
    from backend.parsers.jin10_parser import Jin10Parser, SOURCE_ID as JIN10_ID
    from backend.parsers.clsd_parser import ClsdParser, SOURCE_ID as CLSD_ID
    from backend.parsers.html_generic import HtmlGenericParser, SOURCE_ID as HTML_GENERIC_ID

    register_parser(AHIOT_ID, AihotParser)
    register_parser(JIN10_ID, Jin10Parser)
    register_parser(CLSD_ID, ClsdParser)
    register_parser(HTML_GENERIC_ID, HtmlGenericParser)

    # Phase 1.2: P0 标讯解析器
    from backend.parsers.bid.ccgp import CcgpParser, SOURCE_ID as CCGP_ID
    from backend.parsers.bid.cebpub import CebpubParser, SOURCE_ID as CEBPUB_ID
    from backend.parsers.bid.ggzy import GgzyParser, SOURCE_ID as GGZY_ID
    from backend.parsers.bid.zycg import ZycgParser, SOURCE_ID as ZYCG_ID
    from backend.parsers.bid.chinabidding import ChinabiddingParser, SOURCE_ID as CHINABIDDING_ID

    register_parser(CCGP_ID, CcgpParser)
    register_parser(CEBPUB_ID, CebpubParser)
    register_parser(GGZY_ID, GgzyParser)
    register_parser(ZYCG_ID, ZycgParser)
    register_parser(CHINABIDDING_ID, ChinabiddingParser)


_register_builtin()


__all__ = [
    "BaseSourceParser",
    "RawItem",
    "get_parser",
    "list_parsers",
    "register_parser",
]