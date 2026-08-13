"""AI 安全专题热点数据采集器（Phase 1b 新增）。

继承 :class:`BaseCollector`：

- ``category``  : ``Category.AI_SECURITY``
- ``sources``   : SecurityWeek AI / BleepingComputer AI / Lil'Log / HN AI Security / 安全内参 / FreeBuf AI
- ``timeout``   : 25s
- ``max_items`` : 30（专题领域量级不大，精选即可）

覆盖 AI 安全交叉领域：prompt injection、jailbreak、AI safety、adversarial ML、
model poisoning、AI red team、AI incident、AI regulation、LLM vulnerability。

Phase 13 硬约束：不生成 fallback 数据，源全部失败时返回空列表。
"""
from __future__ import annotations

from typing import Any

from backend.collectors.base import BaseCollector
from backend.domain.enums import Category

AI_SECURITY_SOURCES: list[dict] = [
    # ---- English RSS sources ----
    # 2026-08-02 实测: SecurityWeek RSS 直连 403, 代理 200(17 links), 需 proxy 可修复
    # 当前 feedparser 路径不支持 proxy, 暂 disabled
    {
        "name": "SecurityWeek AI Security",
        "url": "https://www.securityweek.com/ai-security/",
        "rss_url": "https://www.securityweek.com/feed/",
        "score": 83,
        "keywords": ["AI security", "LLM", "machine learning", "adversarial"],
        "renderer": "disabled",
    },
    # 2026-08-02: BleepingComputer AI 直连/代理均 403 (Cloudflare), 不可抓取
    {
        "name": "BleepingComputer AI",
        "url": "https://www.bleepingcomputer.com/tag/artificial-intelligence/",
        "score": 80,
        "keywords": ["AI", "security", "LLM", "vulnerability"],
        "renderer": "disabled",
    },
    # 2026-08-02: Lil'Log RSS 直连/代理均返回 CF 挑战页面(80KB 非 RSS 内容), 不可抓取
    {
        "name": "Lil'Log",
        "url": "https://lilianweng.github.io/",
        "rss_url": "https://lilianweng.github.io/index.xml",
        "score": 88,
        "keywords": ["AI safety", "alignment", "security", "LLM"],
        "renderer": "disabled",
    },
    {
        "name": "HN AI Security",
        "url": "https://news.ycombinator.com/",
        "rss_url": "https://hnrss.org/newest?q=AI+security+OR+LLM+vulnerability+OR+prompt+injection+OR+AI+safety",
        "score": 80,
        "keywords": ["AI security", "LLM", "safety", "vulnerability"],
    },
    # ---- Chinese HTML sources ----
    {
        "name": "安全内参",
        "url": "https://www.secrss.com/",
        "score": 78,
        "keywords": ["AI安全", "人工智能安全", "大模型安全", "LLM"],
    },
    {
        "name": "FreeBuf AI安全",
        "url": "https://www.freebuf.com/",
        "score": 78,
        "keywords": ["AI安全", "LLM安全", "大模型漏洞", "AI"],
    },
]


class AISecurityCollector(BaseCollector):
    """采集 AI 安全 / 大模型安全 / 对抗 ML 专题热点数据。"""

    category = Category.AI_SECURITY
    sources = AI_SECURITY_SOURCES
    timeout = 25
    max_items = 30
    # 专题领域量小，放宽保底阈值
    min_items_threshold = 1

    # Phase 13 硬约束: 不实现 _fallback()。所有源失败时 collect()
    # 直接返回 [], UI 显示"该分类暂无可用资讯"。
    # 真实链接优先于"假装有数据" — 详细约束见 SPEC §3。


__all__ = ["AISecurityCollector", "AI_SECURITY_SOURCES"]