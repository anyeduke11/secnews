"""Item 构建与过滤 Mixin（v1.8 R3 从 base.py 拆出）。

``ItemBuilderMixin`` 承载 raw dict → ``HotspotItem`` 的构建链：

- ``_build_items``     — NAV/CTA 黑名单、长度过滤、Phase 47 时效硬门禁、
  Phase 20 bid_status 提取
- ``_title_relevant``  — Phase 25 分类相关度过滤（委托 keywords 模块）
- ``_mark_fallback``   — fallback 标记工具（Phase 13 后不再自动调用）
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from backend.collectors.keywords import _is_title_relevant_to_category
from backend.domain.models import HotspotItem


class ItemBuilderMixin:
    """BaseCollector 的 item 构建/过滤实现（依赖宿主类的
    ``name`` / ``category`` / ``max_items`` / ``logger``）。"""

    def _build_items(
        self, raw_items: list[dict[str, Any]], source: dict
    ) -> list[HotspotItem]:
        """raw dicts (``_parse_html`` 输出) → ``HotspotItem`` list。

        Bug 2 修复: ``raw["published_at"]`` 优先(由 ``_parse_html`` 从
        meta / JSON-LD / URL slug 提取);缺失时回退到 fetch time。

        Phase 15: ``ingested_at`` = 录入时间(= now),列表按此字段排序。
        ``published_at`` 保留为文章真实发布时间(可能比 ingested_at 早很多,
        当源页面显示历史内容时)。

        Phase 20: ``bid_status`` 字段(仅 category=bid)从标题正则提取。

        Phase 25: title 通用过滤 (导航 CTA / 超短标题 / 纯标点)
        — 修复部门信源(如投资界、新浪财经)抓到"查看更多 >" / "入驻创投号>>>"
        / "今年暑期旅行社" 等与分类无关的标题。
        """
        from backend.domain.enums import Category as _Cat

        # Phase 20: 标讯状态提取器(惰性导入,避免循环)
        _extract_bid_status = None
        if self.category == _Cat.BID:
            from backend.collectors.bid_status import extract_bid_status
            _extract_bid_status = extract_bid_status

        # Phase 25: 通用 title 导航/CTA 黑名单 (所有 category 共用)
        # 防止投资界 / 新浪财经 / 36kr 等综合媒体把侧栏链接误当标题
        _NAV_CTA = re.compile(
            r"查看更多|更多\s*>>|更多\s*>|立即查看|立即申请|"
            r"立即报名|马上了解|点击查看|>>>|>>>\s*$|>>\s*$|"
            r"入驻\s*\S{0,4}$|注册\s*\S{0,4}$|"
            r"查看全部|点击进入|关注我们|关于我们|"
            r"^\s*[Aa][Bb][Oo][Uu][Tt]\s*$|"
            r"^\s*[Cc][Oo][Nn][Tt][Aa][Cc][Tt]\s*$|"
            r"^更多$|^首页$|^登录$|^注册$"
        )
        _MIN_TITLE_LEN = 8  # 短于 8 字符基本都是 nav / breadcrumb
        _MAX_TITLE_LEN = 200  # 长于 200 通常是把段落当标题

        now = datetime.now(timezone.utc)
        items: list[HotspotItem] = []
        skipped = 0
        # Phase 47: 资讯/标讯时效硬门禁 — 本周一 00:00 Asia/Shanghai
        # 2026-08-03: 公众号源 (wechat renderer) 放宽到 30 天,
        #   因为搜狗微信搜索索引的文章日期可能较旧。
        # 2026-08-04: 公众号源收紧到 source.max_age_days(默认 7 天, 硬上限 14 天),
        #   双重门禁(parser 已过滤,这里是 defense-in-depth)。
        from backend.utils.business_days import current_week_start
        renderer = source.get("renderer", "")
        if renderer == "wechat":
            raw_wechat_age = int(source.get("max_age_days", 7) or 7)
            wechat_max_age = max(1, min(raw_wechat_age, 14))  # 硬上限 14
            recency_threshold = now - __import__("datetime").timedelta(days=wechat_max_age)
        else:
            recency_threshold = current_week_start()
        for i, raw in enumerate(raw_items[: self.max_items * 2]):  # 多取些再过滤
            title = (raw.get("title") or "").strip()
            url = (raw.get("url") or "").strip()
            # Phase 25: 通用 title 过滤
            if not title or len(title) < _MIN_TITLE_LEN:
                skipped += 1
                continue
            if len(title) > _MAX_TITLE_LEN:
                skipped += 1
                continue
            if _NAV_CTA.search(title):
                skipped += 1
                continue
            # Phase 25: 分类相关度过滤 (子类可重写 _title_relevant)
            if not self._title_relevant(title, url, source):
                skipped += 1
                continue
            # Bug 2: 优先用 _parse_html 提取的文章发布时间
            # Phase 47: 不再 fallback 到 now — 缺失 published_at 一律拒绝
            #   原因: 嘶吼等 HTML 抓取源偶尔提取不到发布时间, fallback 到
            #   fetch time 会让历史资讯被当作"当周新资讯"入库, 污染首页。
            #   缺失发布时间 = 无法验证时效性 = 拒收 (宁缺毋滥)。
            published_at = raw.get("published_at")
            if published_at is None:
                skipped += 1
                self.logger.debug(
                    f"{source['name']} drop no-published_at item {i}: "
                    f"title={title[:40]!r}"
                )
                continue
            # Phase 47: 早于本周一 00:00 Shanghai → 拒收 (历史资讯)
            # type 兜底: 如果上游传了非 datetime (eg 字符串), 拒收
            if not isinstance(published_at, datetime) or published_at.tzinfo is None:
                skipped += 1
                self.logger.debug(
                    f"{source['name']} drop bad-published_at item {i}: "
                    f"title={title[:40]!r} type={type(published_at).__name__}"
                )
                continue
            if published_at < recency_threshold:
                skipped += 1
                self.logger.debug(
                    f"{source['name']} drop historical item {i}: "
                    f"pub={published_at.isoformat()} < "
                    f"threshold={recency_threshold.isoformat()}"
                )
                continue
            # Phase 20: 标讯状态提取
            bid_status_val = None
            if _extract_bid_status is not None:
                bid_status_val = _extract_bid_status(
                    title,
                    raw.get("summary", "") or "",
                )
            try:
                # P2-7: ID 稳定化 — 原方案 `f"{name}_{source}_{i}"` 中 i 是
                # 抓取列表枚举下标: 源顺序变化 → 同 URL 变新 ID → 重复入库;
                # 内容漂移 → 同 ID 被不同 URL 覆盖 (收藏/标签按 id 关联出错)。
                # 改为: 可读前缀 + URL 指纹哈希 (同 URL 恒同 ID, 跨轮稳定)。
                if raw.get("id"):
                    item_id = raw["id"]
                else:
                    try:
                        from backend.services.data_cleaning import item_id_from_url
                        url_hash = item_id_from_url(raw["url"])
                    except Exception:
                        import hashlib
                        url_hash = hashlib.sha256(
                            str(raw.get("url", "")).encode("utf-8")
                        ).hexdigest()[:12]
                    item_id = f"{self.name}_{source['name']}_{url_hash[:12]}"
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
                        region=raw.get("region"),  # Phase 8: 标讯地区
                        published_at_tz_assumed=bool(
                            raw.get("published_at_tz_assumed", False)
                        ),
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
                f"{source['name']} filtered {skipped} nav/cta/short/irrelevant/no-pub/historical titles"
            )
        return items

    def _title_relevant(
        self, title: str, url: str, source: dict
    ) -> bool:
        """Phase 25: 分类相关度过滤。子类可重写此方法,
        注入自定义过滤逻辑(例如按 source 加白/黑名单)。

        默认实现: 走 ``_CAT_KEYWORDS`` 关键词白名单。
        - ai / finance / startup: 必须命中至少一个关键词才放行
          (阻挡 "查看更多 >" / "演唱会" / "旅行社" 等无关内容)
        - security / bid / github: 默认放行(这些分类用领域专用关键词
          在 collector 内部或 quality gate 里处理)
        """
        return _is_title_relevant_to_category(title, self.category.value)

    def _mark_fallback(
        self, items: list[HotspotItem]
    ) -> list[HotspotItem]:
        """复制 items 并打上 ``is_fallback=True`` + ``"fallback"`` flag。"""
        out: list[HotspotItem] = []
        for item in items:
            flags = list(item.quality_flags)
            if "fallback" not in flags:
                flags.append("fallback")
            out.append(
                item.model_copy(
                    update={"is_fallback": True, "quality_flags": flags}
                )
            )
        return out


__all__ = ["ItemBuilderMixin"]
