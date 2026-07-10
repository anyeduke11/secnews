"""IT / 科技 资讯采集器 (Phase 25 P1)。

继承 :class:`BaseCollector`：

- ``category``  : ``Category.TECH``  (Phase 25 新增分类)
- ``sources``   : IT之家 (ithome.com)
- ``max_items`` : 120 (同其他新闻类)
- ``min_items_threshold`` : 5

IT之家 是国内主流 IT/科技资讯站,内容覆盖:
- 手机/数码/PC 硬件 (iPhone/Android/小米/华为/... 已在 base._CAT_KEYWORDS tech 列表中)
- 软件/系统更新 (Windows/iOS/HarmonyOS)
- 互联网/创业公司动态
- 部分 AI/科技跨界内容 (机器人/无人机/算法)

技术细节
--------
IT之家列表页 (https://www.ithome.com/list/) HTML 结构:
  <ul>
    <li>
      <a class="t" href="..."> 标题 </a>
      <i>2026-07-07 14:30</i>     <!-- 发布时间 -->
    </li>
  </ul>

广告过滤: URL 含 'lapin' 推广前缀 + 标题含 '神券/优惠/补贴/京东' 的丢弃。
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from backend.collectors.base import BaseCollector
from backend.domain.enums import Category
from backend.domain.models import HotspotItem

# IT之家列表页 DOM 解析 (Phase 25 P1)
# 标题选择器: a.t
# 时间选择器: li > i
_TITLE_RE = re.compile(
    r'<a[^>]+class=["\']t["\'][^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_DATE_RE = re.compile(
    r'<i[^>]*>(20\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2})</i>',
)
# 广告/推广关键词 (参考 newsnow 实现)
_AD_KEYWORDS = ("神券", "优惠", "补贴", "京东", "lapin")

TECH_SOURCES: list[dict] = [
    {
        "name": "IT之家",
        "url": "https://www.ithome.com/list/",
        "rss_url": "https://www.ithome.com/rss/",
        "score": 80,
        "renderer": "html",
    },
]


class TechCollector(BaseCollector):
    """IT/科技 资讯采集器 (Phase 25 P1)。"""

    category = Category.TECH
    sources = TECH_SOURCES
    max_items = 120
    min_items_threshold = 5

    def _parse_html(
        self, html: str, source: dict
    ) -> list[dict[str, Any]]:
        """IT之家专用 HTML 解析。

        返回 ``[{"title": ..., "url": ..., "published_at": ...}, ...]``。
        """
        raw_items: list[dict[str, Any]] = []
        for m in _TITLE_RE.finditer(html):
            url, title_html = m.group(1), m.group(2)
            # 清理 HTML tags
            title = re.sub(r"<[^>]+>", "", title_html).strip()
            if not title or not url:
                continue
            # 找同一 li 块内的 <i> 时间
            # m.start() 是 a.t 的开始位置; 找下一个 i 块
            pos = m.end()
            date_match = _DATE_RE.search(html, pos)
            published_at: str | None = None
            if date_match:
                try:
                    dt = datetime.strptime(
                        date_match.group(1), "%Y-%m-%d %H:%M"
                    ).replace(tzinfo=timezone.utc)
                    published_at = dt.isoformat()
                except ValueError:
                    published_at = None

            # 过滤广告/推广
            if "lapin" in url.lower() or any(
                k in title for k in _AD_KEYWORDS
            ):
                continue

            raw_items.append(
                {
                    "title": title,
                    "url": url,
                    "published_at": published_at,
                }
            )
        return raw_items
