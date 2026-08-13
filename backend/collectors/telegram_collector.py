"""Telegram 公开频道热点数据采集器（Phase 11 延迟实现）。

继承 :class:`BaseCollector`：

- ``category``  : ``Category.TECH``
- ``sources``   : Telegram 公开频道 HTML 抓取 (``renderer`` = ``"aiohttp"``)
- ``timeout``   : 30s（默认）

Phase 13 硬约束: 不再生成合成 fallback 数据,源全部失败时直接返回空列表。

这是一个延迟实现（见 Phase 11 spec §3.4）。如果遇到反爬,``collect()``
返回空列表并记录 warning。这是预期行为。
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from backend.collectors.base import BaseCollector
from backend.collectors.id_factory import make_readable_id
from backend.domain.enums import Category
from backend.domain.models import HotspotItem

TELEGRAM_SOURCES: list[dict] = [
    {
        "name": "Telegram",
        "url": "https://t.me/s/",
        "score": 75,
        "keywords": ["tech", "news"],
        "renderer": "aiohttp",
    },
]

# Telegram 公开频道 post URL 模式: https://t.me/<channel>/<post_id>
# 提取数字 post_id (e.g., "12345"),避免 _sanitize 移除路径分隔符
_TELEGRAM_POST_URL_RE = re.compile(r"https://t\.me/[^/]+/(\d+)")

# Telegram 公开频道 HTML 中的 post 链接模式
_TELEGRAM_LINK_RE = re.compile(
    r'<a[^>]*href="(https://t\.me/[^"]+)"[^>]*>([^<]+)</a>',
    re.IGNORECASE,
)


class TelegramCollector(BaseCollector):
    """Telegram 公开频道热点数据采集器。

    使用标准 ``fetch_source()`` 模式（``_parse_html`` + ``_build_items``）。
    延迟实现: 如果遇到反爬,返回空列表并记录 warning。
    """

    category = Category.TECH
    sources = TELEGRAM_SOURCES

    def _parse_html(self, html: str, source: dict) -> list[dict[str, Any]]:
        """解析 Telegram 公开频道 HTML 页面。

        Telegram 公开频道页面 (t.me/s/<channel>) 的 HTML 结构包含
        带有 ``tgme_widget_message`` 类的消息块,每个消息块包含
        一个指向 ``t.me/<channel>/<id>`` 的链接。

        这是一个延迟实现,使用简单的正则匹配提取标题和链接。
        如果遇到反爬,collect() 返回空列表并记录警告。
        """
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for m in _TELEGRAM_LINK_RE.finditer(html):
            url = m.group(1).strip()
            title = m.group(2).strip()

            if not title or not url:
                continue
            if len(title) < 8 or len(title) > 200:
                continue

            key = title[:30]
            if key in seen:
                continue
            seen.add(key)

            # 从 URL 提取数字 post ID (e.g., "12345")
            id_match = _TELEGRAM_POST_URL_RE.search(url)
            post_id = id_match.group(1) if id_match else url.split("/")[-1]

            readable_id = make_readable_id("telegram", "post", post_id)

            items.append({
                "id": readable_id,
                "title": title,
                "summary": "",
                "url": url,
                # 延迟实现,不提取发布时间;使用当前时间占位,
                # _build_items 会据此判断时效性。
                "published_at": datetime.now(timezone.utc),
            })

            if len(items) >= self.max_items:
                break

        return items

    def _build_items(
        self, raw_items: list[dict[str, Any]], source: dict
    ) -> list[HotspotItem]:
        """重写 _build_items 以使用可读 ID。

        ``_parse_html`` 在 raw dict 中设置了 ``id`` 字段(可读 ID 格式
        ``telegram:post:{id}``),此方法直接使用该字段作为
        ``HotspotItem.id``。
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
        week_start = current_week_start()
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
            published_at = raw.get("published_at")
            if published_at is None:
                skipped += 1
                continue
            if not isinstance(published_at, datetime) or published_at.tzinfo is None:
                skipped += 1
                continue
            if published_at < week_start:
                skipped += 1
                continue
            bid_status_val = None
            if _extract_bid_status is not None:
                bid_status_val = _extract_bid_status(
                    title,
                    raw.get("summary", "") or "",
                )
            try:
                # 使用 raw dict 中的 id (可读 ID),否则使用默认格式
                item_id = raw.get("id") or f"{self.name}_{source['name']}_{i}"
                items.append(
                    HotspotItem(
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
                )
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


__all__ = ["TelegramCollector", "TELEGRAM_SOURCES"]