"""独立开发 / 创业热点数据采集器（Phase 3 重构）。

继承 :class:`BaseCollector`:

- ``category``  : ``Category.STARTUP``
- ``sources``   : 36氪 / 虎嗅 / 投资界 / IT 桔子
- ``timeout``   : 20s
- ``max_items`` : 40

外网抓取走 ``BaseCollector.fetch_source`` 默认实现。
Phase 13 硬约束: 不再生成合成 fallback 数据,源全部失败时直接返回空列表。

Phase 34 (2026-07-08) 新增: 投资界 (pedaily.cn) 非资讯标题黑名单。
背景: 投资界首页/频道页混入 "投资人排行榜" 系列条目 (e.g. 2026「投资界
TOP100」投资人、2025「投资界S50女性投资人」等),URL 路径已被全局
``URL_PATH_BLOCKLIST`` 拦截 (pedaily.cn/{YYYY}investor 等),但偶尔有
URL 走 ``/2026investor/index.shtml`` 之类边角路径漏网;此处用标题正则
兜底拦截"投资人排行榜"系列,仅对源 url 含 ``pedaily.cn`` 的条目生效。
"""
from __future__ import annotations

import re

from backend.collectors.base import BaseCollector
from backend.domain.enums import Category

STARTUP_SOURCES: list[dict] = [
    {"name": "36氪", "url": "https://36kr.com/", "rss_url": "https://36kr.com/feed", "score": 78},
    {"name": "虎嗅", "url": "https://www.huxiu.com/", "rss_url": "https://www.huxiu.com/rss/0.xml", "score": 76},
    {"name": "投资界", "url": "https://www.pedaily.cn/", "score": 75},
    {"name": "IT桔子", "url": "https://www.itjuzi.com/", "score": 72},
]


# ---------------------------------------------------------------------------
# Phase 34 (2026-07-08): 投资界 (pedaily.cn) 非资讯 标题 黑名单
# ---------------------------------------------------------------------------
# URL 路径已在全局 URL_PATH_BLOCKLIST 拦截 (pedaily.cn/{YYYY}{investor|S50|F40} 等),
# 此处仅兜底拦截标题中"投资人排行榜"系列。
# 仅对源 url 含 ``pedaily.cn`` 的条目生效。
# ---------------------------------------------------------------------------
_PEDAILY_RANKING_TITLE_RE = re.compile(
    r"投资界(TOP100|S50|F40|独角兽)"  # 投资界XXX 排名
    r"|F40中国青年投资人"  # 标题前缀
    r"|独角兽榜单"  # 独角兽榜单
)


class StartupCollector(BaseCollector):
    """采集独立开发 / 创业领域热点数据。"""

    category = Category.STARTUP
    sources = STARTUP_SOURCES
    timeout = 20
    max_items = 40

    # Phase 13 硬约束: 不再实现 _fallback()。所有源失败时 collect()
    # 直接返回 [],UI 显示"该分类暂无可用资讯"。
    # 真实链接优先于"假装有数据" — 详细约束见 SPEC §3。

    def _title_relevant(
        self, title: str, url: str, source: dict
    ) -> bool:
        """Phase 34 (2026-07-08) override: 投资界标题兜底黑名单。

        在 BaseCollector 默认实现基础上,叠加投资界特定的:
        - 标题正则 (投资界TOP100 / S50 / F40 / 独角兽)
        仅对源 url 含 ``pedaily.cn`` 的条目生效,其他源走默认实现。
        """
        from backend.collectors.base import _is_title_relevant_to_category

        if not _is_title_relevant_to_category(title, self.category.value):
            return False
        src_url = source.get("url", "") if isinstance(source, dict) else ""
        if "pedaily.cn" in src_url:
            if _PEDAILY_RANKING_TITLE_RE.search(title or ""):
                return False
        return True


__all__ = ["StartupCollector", "STARTUP_SOURCES"]
