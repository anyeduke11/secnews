"""AI 资讯热点数据采集器（Phase 3 重构, Phase 25 P1 扩容, Phase 26 加 RSS, 2026-07-28 加 AGI Hunt）。

继承 :class:`BaseCollector`：

- ``category``  : ``Category.AI``
- ``sources``   : HackerNews / 量子位 / 36氪AI / 机器之心 / AIhot / 小互AI / AGI Hunt
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

Phase 27 (2026-07-28): 新增 AGI Hunt RSS 源 (https://agihunt.info/feed.xml)
  AI 快讯聚合站, X/公众号/Reddit/GitHub/HF/YouTube 多信源采集 + AI 汇总整理。
  走 Phase 22 RSS 路由,结构稳定 (<item> 含 title/link/pubDate/dc:creator/description)。
  站点首页是 SPA 壳子, 抓 HTML 只能拿到导航/今日焦点 SSR 副本;
  RSS 路径直接拿完整文章列表,避开 React 渲染依赖。
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
    # 2026-08-02 实测: 量子位(qbitai.com) WAF 封禁(ERR_CONNECTION_RESET, 直连/代理均有 CF 404 页面), 不可抓取
    {
        "name": "量子位",
        "url": "https://www.qbitai.com/",
        "score": 78,
        "keywords": ["AI", "大模型"],
        "renderer": "disabled",
    },
    {
        "name": "36氪AI",
        "url": "https://36kr.com/information/AI",
        "score": 75,
        "keywords": ["AI"],
        "renderer": "disabled",  # 2026-08-02: JS SPA 页面, aiohttp 只能拿到 3 个导航链接; 36kr 主站 RSS 已由 startup 分类覆盖
    },
    # 2026-08-02 实测: 机器之心(jiqizhixin.com) CAPTCHA 反爬, 12KB 仅 3 links, 不可抓取
    {
        "name": "机器之心",
        "url": "https://www.jiqizhixin.com/",
        "score": 78,
        "keywords": ["AI", "模型"],
        "renderer": "disabled",
    },
    # ===== AI 公众号 (2026-08-02 新增, 走 sogou weixin 搜索) =====
    {
        "name": "新智元",
        "account_name": "新智元",
        "score": 82,
        "renderer": "wechat",
    },
    {
        "name": "硅星人",
        "account_name": "硅星人",
        "score": 78,
        "renderer": "wechat",
    },
    {
        "name": "极客公园",
        "account_name": "极客公园",
        "score": 76,
        "renderer": "wechat",
    },
    {
        "name": "爱范儿",
        "account_name": "爱范儿",
        "score": 74,
        "renderer": "wechat",
    },
    {
        "name": "品玩",
        "account_name": "品玩",
        "score": 72,
        "renderer": "wechat",
    },
    {
        "name": "AI科技评论",
        "account_name": "AI科技评论",
        "score": 72,
        "renderer": "wechat",
    },
# Phase 25 P1: AIhot 每日 AI 热点聚合 (https://aihot.virxact.com)
    # 必须带特定 User-Agent 否则返回 403 (空 UA / 旧 Chrome 都被拦)
    # V1.9: 新增 rss_url, 走 RSS 路径更稳定 (JSON API 保留作为 fallback)
    {
        "name": "AIhot",
        "url": "https://aihot.virxact.com/",
        "rss_url": "https://aihot.virxact.com/feed/full.xml",
        "api_url": "https://aihot.virxact.com/api/public/items?mode=all&take=30",
        "score": 82,
        "keywords": ["AI"],
        "renderer": "json",  # JSON API (Phase 25 P1), RSS 优先
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
    # Phase 27 (2026-07-28): AGI Hunt AI 快讯聚合站 (agihunt.info)
    # 描述: 全天候 AI 快讯, X/公众号/Reddit/GitHub/HF/YouTube 多信源 + AI 汇总
    # 路由: Phase 22 RSS 路径 (源首页是 SPA 壳, HTML 抓取只能拿到 SSR 副本;
    #       RSS /feed.xml 提供完整 <item> 列表, 含 title/link/pubDate/dc:creator)
    # 与 小互AI 区别: 小互AI 偏长文解读, AGI Hunt 偏实时快讯 + 事件聚簇,
    #               标题更短、信息密度更高, 与 AIhot 形成"快讯"+"深度"互补。
    {
        "name": "AGI Hunt",
        "url": "https://agihunt.info/",
        "rss_url": "https://agihunt.info/feed.xml",
        "score": 78,
        "keywords": ["AI", "AGI", "快讯", "事件聚簇"],
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


__all__ = ["AI_SOURCES", "AICollector"]
