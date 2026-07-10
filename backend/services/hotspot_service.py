"""Phase 4 HotspotService — 列表 / 详情 / 类别计数（业务编排层）。

设计
----
- 列表查询：``list_cache`` 缓存 + HotspotRepository
- 详情查询：``detail_cache`` 缓存
- 类别计数：``static_cache`` 缓存
- 所有缓存失败 / miss → 走 DB；不抛异常
"""
from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Optional

from backend.logging_config import logger

from backend.cache import detail_cache, list_cache, static_cache
from backend.domain.enums import Category, TimeRange
from backend.domain.models import HotspotItem
from backend.exceptions import InvalidParamException, NotFoundException
from backend.repository.hotspot_repo import HotspotRepository

_hrepo = HotspotRepository()

# ---------------------------------------------------------------------------
# url_check_status 优先级 (Phase 45): verified=0 (winner, key 最小), pending=2 (loser)
# 与 backend/quality/duplicate_gate.py:_URL_CHECK_RANK 保持一致。
# 用 ``min`` 选 winner (Python sorted 升序 → key 最小者胜)。
# ---------------------------------------------------------------------------
_URL_CHECK_RANK = {
    "verified": 0,
    "mismatch": 1,
    "skipped": 1,
    "pending": 2,
    "unreachable": 2,
    None: 2,
}

# ---------------------------------------------------------------------------
# Category <-> id string 映射
# ---------------------------------------------------------------------------
_VALID_CATEGORIES: set[str] = {c.value for c in Category} | {"all"}


def _validate_category(cat: str) -> str:
    if cat not in _VALID_CATEGORIES:
        raise InvalidParamException(
            f"category must be one of {sorted(_VALID_CATEGORIES)}, got {cat!r}"
        )
    return cat


def _validate_time_range(tr: str) -> TimeRange:
    try:
        return TimeRange(tr)
    except ValueError as e:
        raise InvalidParamException(f"invalid time_range: {tr}") from e


# ---------------------------------------------------------------------------
# cursor 编解码（base64 of {"id", "ts"}）
# ---------------------------------------------------------------------------
def encode_cursor(item: HotspotItem) -> str:
    """``HotspotItem → base64 cursor``。

    Phase 15: cursor 基于 ingested_at(列表排序字段),而非 published_at。
    """
    ts = item.ingested_at or item.fetched_at
    raw = json.dumps(
        {"id": item.id, "ts": ts.isoformat()},
        ensure_ascii=False,
    )
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_cursor(cursor: str) -> tuple[str, str]:
    """``cursor → (id, ingested_at_iso)``。无效时抛 InvalidParamException。"""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        obj = json.loads(raw)
        return str(obj["id"]), str(obj["ts"])
    except (ValueError, KeyError, TypeError) as e:
        raise InvalidParamException(f"invalid cursor: {cursor[:30]}") from e


# ---------------------------------------------------------------------------
# HotspotService
# ---------------------------------------------------------------------------
class HotspotService:
    """业务编排：cache → repository。"""

    MAX_LIMIT = 200
    DEFAULT_LIMIT = 50

    # ------------------------------------------------------------------
    def list_hotspots(
        self,
        category: str = "all",
        time_range: str = "7d",
        cursor: Optional[str] = None,
        limit: int = DEFAULT_LIMIT,
        keyword: str = "",
    ) -> dict:
        """列表查询。

        Returns
        -------
        dict with keys: items, next_cursor, total, category, time_range,
        keyword, fetched_at, category_counts

        Phase 9 修复：同 url 多条 item 时按 (is_fallback, quality_score,
        title_len, fetched_at, id) 排序去重，只保留 winner 一条，
        解决"两张卡片同 url 不同 title"重复显示问题。

        Phase 24 add: ``balanced`` 模式 (cursor 为空时默认开启)
        — 解决"全部热点只显示网络安全资讯"问题: 因为 security collector 跑得最久,
        ingested_at 晚于其他 5 分类 2-3 秒, 单一 ingested_at DESC 排序
        必然让 security 占满 limit 条。balanced 模式按分类各取 max(limit/N, 5) 条
        再按 ingested_at DESC 混合, 保证 6 个分类都能露出。
        """
        _validate_category(category)
        tr = _validate_time_range(time_range)
        limit = min(max(1, limit), self.MAX_LIMIT)

        # balanced 模式: 只在 cursor=None (首页) 且 category=="all" 时启用
        # 翻页 (cursor 有值) 时回退到原行为, 避免分类均衡的 cursor 实现复杂度
        balanced = (
            cursor is None
            and not keyword
            and category == "all"
        )

        cache_key = (
            f"hotspots:list:{category}:{tr.value}"
            f":{cursor or ''}:{limit}:{keyword}:{'bal' if balanced else 'raw'}"
        )
        if cache_key in list_cache:
            return list_cache[cache_key]

        # 把 base64 服务层 cursor 转成 repo 内部 cursor (``<unix_ts>_<id>``)
        repo_cursor = self._to_repo_cursor(cursor)

        cat_enum = None if category == "all" else Category(category)
        if balanced:
            items, next_cursor_raw = self._query_balanced(tr, limit)
        else:
            items, next_cursor_raw = _hrepo.query(
                category=cat_enum,
                time_range=tr,
                keyword=keyword,
                cursor=repo_cursor,
                limit=limit,
            )

        # Phase 9 修复:同 url 多条 → 保留 winner
        items = self._dedupe_by_url(items)

        # next_cursor 基于过滤后的最后一条
        next_cursor = (
            encode_cursor(items[-1]) if (next_cursor_raw and items) else None
        )

        # Phase 40: StatsPanel/TopNav 跟随当前 time_range (与 Grid 口径一致)
        cat_counts = self.count_by_category(tr)

        # Phase 42 修复: total 用去重 url 数, 与 items 口径一致
        # 之前用 count_in_range 返回行数 (同 url 多次入库会算多次),
        # 导致 "X / 841" 而 X 远小于 841, 分页器提前显示 "已是最后一页"
        cat_for_count = None if category == "all" else category
        true_total = _hrepo.count_unique_urls_in_range(tr, category=cat_for_count)

        # Phase 39: 最近一次采集的产出
        from backend.services.collection_service import get_latest_run as _get_latest_run
        latest = _get_latest_run()
        latest_iso = latest["at"].isoformat() if latest["at"] is not None else None

        result = {
            "version": "1.2.0",
            "items": [item.model_dump(mode="json") for item in items],
            "next_cursor": next_cursor,
            "total": true_total,  # 真实总数 (用于分页 "X / Y")
            "category": category,
            "time_range": tr.value,
            "keyword": keyword,
            "category_counts": cat_counts,  # 本周 (D7) — 与 Grid time_range 解耦
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            # Phase 39: 新增 — 最近一轮 run_once() 的产出
            "latest_ingestion_count": int(latest["count"]),
            "latest_ingestion_at": latest_iso,
        }
        list_cache[cache_key] = result
        return result

    @staticmethod
    def _query_balanced(tr, limit: int) -> tuple[list[HotspotItem], bool]:
        """分类均衡查询: 6 分类各取 N 条, 混合按 ingested_at DESC 排, **先 dedupe 再 take**。

        解决 security 排前挤掉其他 5 分类的问题。

        Phase 24: 用 ceil(limit/N) + min 5 保底, 即使 limit 很小也能保证每类至少
        5 条候选。bid 和 github 经常 0 条, 不影响其他分类配额。

        Phase 35: 移除 ``Category.TECH``(ai query 已合并 tech), 避免 tech 重复
        入桶导致均衡后 tech 条目翻倍挤掉其他分类。

        Phase 42 修复:
        - ``per_cat = max(limit, 20)`` (Phase 24 用 limit//6=16, dedupe 后 < 100, 用户报
          "已显示 83 条" 而非 100; Phase 24 -> 这里 limit*2//5 也仍少)
        - **先 dedupe 再 take limit** (之前 take 再 dedupe, dedupe 后会 < limit, 翻页数据
          不稳定; 改后保证每页稳定 = limit 条)
        """
        per_cat = max(limit, 20)
        merged: list[HotspotItem] = []
        _log = logger.bind(component="hotspot_service")
        for cat in (
            Category.AI,
            Category.SECURITY,
            Category.FINANCE,
            Category.STARTUP,
            Category.BID,
            Category.GITHUB,
        ):
            try:
                items, _ = _hrepo.query(
                    category=cat,
                    time_range=tr,
                    limit=per_cat,
                )
                merged.extend(items)
            except Exception as e:
                # 单分类失败不阻塞, 降级为该分类 0 条
                _log.warning(
                    f"balanced query failed for {cat.value}: {e}"
                )
        # 全局按 ingested_at DESC 排
        merged.sort(
            key=lambda it: it.ingested_at or it.published_at,
            reverse=True,
        )
        # Phase 42 关键修复: 先 dedupe 再 take limit, 保证分页数据量稳定
        merged = HotspotService._dedupe_by_url(merged)
        sliced = merged[:limit]
        has_more = len(merged) >= limit  # 候选 ≥ limit → 可能有下一页
        return sliced, has_more

    @staticmethod
    def _dedupe_by_url(items: list[HotspotItem]) -> list[HotspotItem]:
        """同 url 重复时按 5 级优先级保留 winner (Phase 45 修复)。

        优先级 (从高到低, Phase 45):
        1. ``url_check_status=verified`` 最优先 (详情页 ``<title>`` 验过)
        2. ``is_fallback=False`` 优先
        3. ``quality_score`` 高优先
        4. ``fetched_at`` 较新优先
        5. ``id`` 字典序小优先 (兜底)

        保留原顺序 (winner 占据首个 url 出现位置)。

        Phase 45 修复: 移除 ``title_len`` 排序 key — 长 title 不等于真 title,
        曾导致同 URL 重复入库时错把 list 页抓到的长 title 摘要当 winner。
        """
        if not items:
            return items
        seen_urls: dict[str, HotspotItem] = {}
        winner_order: list[str] = []  # 记录 url 首次出现顺序

        def _sort_key(it: HotspotItem) -> tuple:
            # url_check_status 优先级: verified=0 (winner, key 最小), pending=2 (loser)
            url_check_rank = _URL_CHECK_RANK.get(it.url_check_status, 2)
            return (
                url_check_rank,                          # 0=verified(winner)
                1 if it.is_fallback else 0,              # 0=not_fallback(winner, key 小)
                -int(it.quality_score or 0),             # 高 quality_score → key 小
                -int(it.fetched_at.timestamp() if it.fetched_at else 0),
                it.id,                                   # 字典序小优先
            )

        for it in items:
            u = str(it.url)
            if u not in seen_urls:
                seen_urls[u] = it
                winner_order.append(u)
            else:
                # Phase 45: 用 min 选 winner (key 最小者胜)
                if _sort_key(it) < _sort_key(seen_urls[u]):
                    seen_urls[u] = it

        return [seen_urls[u] for u in winner_order]

    @staticmethod
    def _to_repo_cursor(cursor: Optional[str]) -> Optional[str]:
        """把 base64 服务层 cursor → repo 的 ``<unix_ts>_<id>`` 格式。

        None / 空 → None; 无效 → 抛 ``InvalidParamException`` (HTTP 400)。
        """
        if not cursor:
            return None
        cursor_id, ts_iso = decode_cursor(cursor)  # 失败 → InvalidParamException
        try:
            ts_int = int(datetime.fromisoformat(ts_iso).timestamp())
        except (TypeError, ValueError) as e:
            raise InvalidParamException(
                f"invalid cursor timestamp: {ts_iso!r}"
            ) from e
        return f"{ts_int}_{cursor_id}"

    # ------------------------------------------------------------------
    def get_hotspot(self, id_: str) -> dict:
        """详情查询。"""
        cache_key = f"hotspots:detail:{id_}"
        if cache_key in detail_cache:
            return detail_cache[cache_key]

        item = _hrepo.get_by_id(id_)
        if item is None:
            raise NotFoundException(f"hotspot {id_!r} not found")

        result = {
            "version": "1.2.0",
            "item": item.model_dump(mode="json"),
            "fetched_at": datetime.utcnow().isoformat() + "Z",
        }
        detail_cache[cache_key] = result
        return result

    # ------------------------------------------------------------------
    def count_by_category(self, time_range: TimeRange = TimeRange.D7) -> dict[str, int]:
        """每个 category 在指定 time_range 内的热点数。走 static_cache (per-time_range)。

        Phase 40 变更: 接收 ``time_range`` 参数, StatsPanel/TopNav 跟随当前
        time_range (H24/D3/D7/D30), 与 Grid 保持口径一致。
        缓存 key 包含 time_range.value, 切换时间窗不会读到旧值。
        """
        cache_key = f"hotspots:count_by_category:{time_range.value}"
        if cache_key in static_cache:
            return static_cache[cache_key]
        result = _hrepo.count_by_category(time_range=time_range)
        static_cache[cache_key] = result
        return result


__all__ = ["HotspotService", "encode_cursor", "decode_cursor"]
