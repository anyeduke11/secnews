"""AI 资讯热点数据采集器（Phase 3 重构, Phase 25 P1 扩容, Phase 26 加 RSS）。

继承 :class:`BaseCollector`：

- ``category``  : ``Category.AI``
- ``sources``   : HackerNews / 量子位 / 36氪AI / 机器之心 / AIhot / 小互AI
- ``timeout``   : 20s（AI 站点大多有 WAF，不宜过长）
- ``max_items`` : 50 (Phase 25 P1: 40 → 50 接住 AIhot)

外网抓取走 ``BaseCollector.fetch_source`` 默认实现（HTML + 标题链接解析）。
Phase 13 硬约束: 不再生成合成 fallback 数据,源全部失败时直接返回空列表。

Phase 25 P1:
- AIhot (aihot.virxact.com) 走 JSON API 路径
  ``https://aihot.virxact.com/api/public/items?mode=all&take=30``
  响应 ``{"items": [{"id", "title", "url", "source", "publishedAt", "summary"}]}``
  通过 ``_parse_json`` 转 raw_items, 走通用 ``_build_items`` 过滤。

Phase 26: 新增 小互AI RSS 源 (https://best.xiaohu.ai/rss.xml)
  走 Phase 22 RSS 路由 (源含 ``rss_url`` 字段 → ``_fetch_rss`` → feedparser)。
  RSS 路径自动避开首页导航/备案链接干扰,直接拿 article 列表。
"""
from __future__ import annotations

from typing import Any

from backend.collectors.base import BaseCollector
from backend.domain.enums import Category

AI_SOURCES: list[dict] = [
    {
        "name": "HackerNews",
        "url": "https://news.ycombinator.com/",
        "rss_url": "https://hnrss.org/newest",
        "score": 80,
        "keywords": ["AI", "GPT", "LLM"],
    },
    {
        "name": "量子位",
        "url": "https://www.qbitai.com/",
        "score": 78,
        "keywords": ["AI", "大模型"],
        "renderer": "crawl4ai",  # Phase 14: 反爬 + JS 渲染
    },
    {
        "name": "36氪AI",
        "url": "https://36kr.com/information/AI",
        "score": 75,
        "keywords": ["AI"],
        "renderer": "crawl4ai",  # Phase 14: 反爬 + JS 渲染
    },
    {
        "name": "机器之心",
        "url": "https://www.jiqizhixin.com/",
        "rss_url": "https://www.jiqizhixin.com/rss",
        "score": 78,
        "keywords": ["AI", "模型"],
        "renderer": "crawl4ai",
    },
    # Phase 25 P1: AIhot 每日 AI 热点聚合 (https://aihot.virxact.com)
    # 必须带特定 User-Agent 否则返回 403 (空 UA / 旧 Chrome 都被拦)
    {
        "name": "AIhot",
        "url": "https://aihot.virxact.com/",
        "api_url": "https://aihot.virxact.com/api/public/items?mode=all&take=30",
        "score": 82,
        "keywords": ["AI"],
        "renderer": "json",  # JSON API (Phase 25 P1)
        "headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0.0.0 Safari/537.36 "
                "aihot-skill/0.2.0 newsnow/0.0.40"
            )
        },
    },
    # Phase 26: 小互AI 解读站 (best.xiaohu.ai)
    # 走 Phase 22 RSS 路径 → feedparser,跳过 HTML 抓取,避免导航/备案链接干扰。
    # 标题/URL/时间来自 <item>,结构稳定,质量高。
    {
        "name": "小互AI",
        "url": "https://best.xiaohu.ai/",
        "rss_url": "https://best.xiaohu.ai/rss.xml",
        "score": 80,
        "keywords": ["AI", "解读"],
    },
]


class AICollector(BaseCollector):
    """采集 AI / 大模型 / 科技领域热点数据。"""

    category = Category.AI
    sources = AI_SOURCES
    timeout = 20
    max_items = 50  # Phase 25 P1: 40 → 50 接住 AIhot

    def _parse_json(
        self, data: Any, source: dict
    ) -> list[dict[str, Any]]:
        """AIhot JSON API 解析 (Phase 25 P1)。

        响应格式:
          {"items": [
              {"id": "...", "title": "...", "url": "...",
               "source": "...", "publishedAt": "2026-07-07T...",
               "summary": "..."}, ...
          ]}
        """
        items_field = (data or {}).get("items") or []
        out: list[dict[str, Any]] = []
        for entry in items_field:
            if not isinstance(entry, dict):
                continue
            title = (entry.get("title") or "").strip()
            url = (entry.get("url") or "").strip()
            if not title or not url:
                continue
            pub = entry.get("publishedAt")
            out.append(
                {
                    "title": title,
                    "url": url,
                    "published_at": pub,
                }
            )
        return out

    # Phase 13 硬约束: 不再实现 _fallback()。所有源失败时 collect()
    # 直接返回 [],UI 显示"该分类暂无可用资讯"。
    # 真实链接优先于"假装有数据" — 详细约束见 SPEC §3。


__all__ = ["AICollector", "AI_SOURCES"]
