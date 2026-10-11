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
import time
from datetime import datetime, timedelta, timezone

from backend.cache import detail_cache, list_cache, static_cache
from backend.domain.enums import Category, TimeRange
from backend.domain.models import HotspotItem
from backend.exceptions import InvalidParamException, NotFoundException
from backend.logging_config import logger
from backend.repository.hotspot_repo import (
    HotspotRepository,
    interest_signal_stats_by_axis,
)
from backend.version import APP_VERSION as API_VERSION

_hrepo = HotspotRepository()

# ---------------------------------------------------------------------------
# DEV-0315: 内容偏好 (类目 / 来源) — feed 排序第二轴 (A+B 整合, 显式、只升降不删)
#
# 与「实践域」(interest.practice_domains, 10 个安全方向) 是**两根正交的轴**:
#   实践域答「这条安全内容属于哪个方向」; 内容偏好答「这类/这家内容我多要或少要」。
# 语义: 显式声明 (非统计推断), 只改排序不影响可见性 (条目永远可达)。
# 兼容: 无配置 (两表皆空) → 因子恒 1.0 → 排序与既有版本完全一致。
# ---------------------------------------------------------------------------
CONTENT_PREF_KEY = "interest.content_preferences"
PREF_LEVELS: tuple[str, str, str] = ("more", "normal", "less")
# 三级因子: 类目与来源共用同一幅度表 (来源粒度更细时可再拆, 当前保持简单可预期)
PREF_MULT: dict[str, float] = {"more": 1.15, "normal": 1.0, "less": 0.78}


def load_content_preferences() -> dict:
    """读 ``interest.content_preferences`` (settings.kv)。

    形状 ``{"categories": {cat: level}, "sources": {source: level}}``。
    只保留合法 level (more/normal/less) 的条目; 空/损坏/读取失败 → {} (排序=现状)。
    同步 sqlite 读 — 调用方须放 thread pool (与 ``_load_interest_domains`` 同约定)。
    """
    try:
        from backend.repository.settings_repo import SettingsRepository

        raw = SettingsRepository().get(CONTENT_PREF_KEY, {})
    except Exception as e:
        logger.warning(f"interest.content_preferences read failed, prefs disabled: {e}")
        return {}
    return _norm_content_preferences(raw)


def _norm_content_preferences(raw: dict | None) -> dict[str, dict[str, str]]:
    """归一化偏好 (PATCH 写入前 + 读取后统一口径): 去 normal / 非法 level / 空或非法 key / 空轴。"""
    out: dict[str, dict[str, str]] = {}
    if not isinstance(raw, dict):
        return out
    for axis in ("categories", "sources"):
        table = raw.get(axis)
        if isinstance(table, dict):
            clean = {
                k: v for k, v in table.items()
                if isinstance(k, str) and k.strip() and v in PREF_LEVELS and v != "normal"
            }
            if clean:
                out[axis] = clean
    return out


def content_preference_signature(prefs: dict | None) -> str:
    """偏好指纹 (缓存键片段): 轴内按 key 排序拼接, 保证同配置同 key。"""
    if not prefs:
        return ""
    parts: list[str] = []
    for axis in ("categories", "sources"):
        table = prefs.get(axis) or {}
        parts.append(f"{axis}:" + ",".join(f"{k}={table[k]}" for k in sorted(table)))
    return "|".join(parts)


# ── DEV-0316: 内容偏好自动推导 (统计兜底, 免手动配置) ──────────────
# 从已有行为信号 (like/dislike/view/favorite…) 按类目/来源聚合净分, 达阈值自动
# 生成偏好喂给 feed 排序 —— 与兴趣引擎"点赞即学习"同族, 用户零配置就有效果。
# 手动偏好 (interest.content_preferences) 与 LLM 采纳项**覆盖**自动推导 (手动优先)。
AUTO_PREF_WINDOW_DAYS = 30
AUTO_PREF_MIN_EVENTS = 3     # 证据下限: 交互不足不自动设 (防单次误触)
AUTO_PREF_MORE_NET = 3.0     # 净分 ≥ +3 (≈2 赞 或 6 view) → more
AUTO_PREF_LESS_NET = -1.5    # 净分 ≤ -1.5 (≈1 踩) → less (降权门槛低于升权: 抑噪优先)
_AUTO_PREF_TTL_S = 300.0     # 5min TTL (与兴趣引擎聚合同频, feed 每请求不重算)
_auto_pref_cache: dict[str, object] = {"ts": 0.0, "data": {}}


def _level_from_stats(stats: dict[str, dict]) -> dict[str, str]:
    """净分表 → 三级偏好 (仅达证据下限且净分越阈的 key; normal 不输出)。"""
    out: dict[str, str] = {}
    for key, s in stats.items():
        if not key or s["events"] < AUTO_PREF_MIN_EVENTS:
            continue
        net = s["net"]
        if net >= AUTO_PREF_MORE_NET:
            out[key] = "more"
        elif net <= AUTO_PREF_LESS_NET:
            out[key] = "less"
    return out


def derive_auto_content_preferences(*, force: bool = False) -> dict[str, dict[str, str]]:
    """从行为信号自动推导 {categories:{key:level}, sources:{key:level}} (5min TTL)。

    失败 (DB/聚合异常) 降级 {} —— 自动层缺席不影响手动偏好与既有排序。
    """
    now = time.monotonic()
    if not force and _auto_pref_cache["data"] and (now - float(_auto_pref_cache["ts"])) < _AUTO_PREF_TTL_S:
        return _auto_pref_cache["data"]  # type: ignore[return-value]
    since = (datetime.now(timezone.utc) - timedelta(days=AUTO_PREF_WINDOW_DAYS)).isoformat()
    result: dict[str, dict[str, str]] = {}
    cats = _level_from_stats(interest_signal_stats_by_axis("category", since))
    srcs = _level_from_stats(interest_signal_stats_by_axis("source", since))
    if cats:
        result["categories"] = cats
    if srcs:
        result["sources"] = srcs
    _auto_pref_cache["ts"] = now
    _auto_pref_cache["data"] = result
    return result


def invalidate_auto_content_preferences() -> None:
    """清自动偏好缓存 (偏好写入 / 信号变更后调用, 下次读重算)。"""
    _auto_pref_cache["ts"] = 0.0
    _auto_pref_cache["data"] = {}


def effective_content_preferences() -> dict[str, dict[str, str]]:
    """feed 实际生效的偏好 = 自动推导 ∪ 手动覆盖 (手动逐 key 优先)。

    合并语义: 手动设了的 key 以手动为准 (含"手动把自动降权的项改回 more");
    手动未碰的 key 沿用自动。两表皆空 → {} (排序退化原序)。
    """
    auto = derive_auto_content_preferences()
    explicit = load_content_preferences()
    merged: dict[str, dict[str, str]] = {}
    for axis in ("categories", "sources"):
        table = dict(auto.get(axis) or {})
        table.update(explicit.get(axis) or {})
        if table:
            merged[axis] = table
    return merged


def _rank_items(
    items: list,
    *,
    practice_multiplier: dict[str, float] | None,
    boost_set: set[str],
    cat_prefs: dict[str, str],
    src_prefs: dict[str, str],
) -> list:
    """三因子复合**稳定降序**重排 (DEV-0176/0182/0315)。

    键 = 实践域乘子 × 内容偏好(类目) × 内容偏好(来源), 见 PREF_MULT。
    无任何因子 (三者皆空) → 原序返回 (兼容: 排序退化现状)。
    同键保持原相对次序 (Python stable sort) —— 这是「只升不删」的实现基础。

    注意: 必须在**切片/分页之前**调用才能影响"选哪条" (否则只是页内重排)。
    """
    if not (practice_multiplier or boost_set or cat_prefs or src_prefs):
        return items
    from backend.services.auto_classifier import classify_practice_domain

    def key(it) -> float:
        pd = classify_practice_domain([], title=getattr(it, "title", "") or "")
        if practice_multiplier:
            m = practice_multiplier.get(pd or "", 1.0)
        else:
            m = PREF_MULT["more"] if pd in boost_set else 1.0
        cat = getattr(it, "category", None)
        cat = getattr(cat, "value", cat) or ""
        m *= PREF_MULT.get(cat_prefs.get(cat, "normal"), 1.0)
        m *= PREF_MULT.get(src_prefs.get(getattr(it, "source", "") or "", "normal"), 1.0)
        return m

    return sorted(items, key=key, reverse=True)


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
        cursor: str | None = None,
        limit: int = DEFAULT_LIMIT,
        keyword: str = "",
        source: str | None = None,  # v1.9.1: 来源筛选
        exclude_category: str | None = None,  # DEV-0175: 工作台聚焦裁决 (前端默认排除 bid)
        boost_practice_domains: list[str] | None = None,  # DEV-0176 T0.4: 兴趣域加权 (降权不删)
        practice_multiplier: dict[str, float] | None = None,  # DEV-0182: 兴趣引擎连续乘子 (优先于 boost)
        content_preferences: dict | None = None,  # DEV-0315: 内容偏好 (类目/来源) 第二轴因子
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
            and not source
            and category == "all"
        )

        mult_key = (
            ",".join(f"{d}:{m}" for d, m in sorted(practice_multiplier.items()))
            if practice_multiplier else ""
        )
        pref_key = content_preference_signature(content_preferences)
        cache_key = (
            f"hotspots:list:{category}:{tr.value}"
            f":{cursor or ''}:{limit}:{keyword}:{source or ''}"
            f":{exclude_category or ''}"
            f":{','.join(sorted(boost_practice_domains)) if boost_practice_domains else ''}"
            f":{mult_key}"
            f":{pref_key}"
            f":{'bal' if balanced else 'raw'}"
        )
        if cache_key in list_cache:
            return list_cache[cache_key]

        # 把 base64 服务层 cursor 转成 repo 内部 cursor (``<unix_ts>_<id>``)
        repo_cursor = self._to_repo_cursor(cursor)

        # DEV-0315: 排序三因子 (实践域 × 内容偏好类目 × 内容偏好来源) 在**查询前**备好 —
        # balanced 路径须在切片前用它排序候选池, 否则偏好只作用于页内重排 (≈无效果)。
        boost_set = {d for d in (boost_practice_domains or []) if d}
        cat_prefs = (content_preferences or {}).get("categories") or {}
        src_prefs = (content_preferences or {}).get("sources") or {}

        cat_enum = None if category == "all" else Category(category)
        if balanced:
            items, next_cursor_raw = self._query_balanced(
                tr, limit, exclude_category,
                practice_multiplier=practice_multiplier,
                boost_set=boost_set, cat_prefs=cat_prefs, src_prefs=src_prefs,
            )
        else:
            items, next_cursor_raw = _hrepo.query(
                category=cat_enum,
                time_range=tr,
                keyword=keyword,
                cursor=repo_cursor,
                limit=limit,
                source=source,
                exclude_category=exclude_category,
            )

        # Phase 9 修复:同 url 多条 → 保留 winner
        items = self._dedupe_by_url(items)

        # next_cursor 锚定页内**最早**条目 (时序基准)
        # (DEV-0176 T0.4 / DEV-0315: 必须取加权重排前的原始时序位置, 否则置顶会
        #  破坏翻页游标的时序连续性。取"最早一条"而非"末条": 非 balanced 路径两者
        #  等价 (页本身时序有序); balanced+偏好路径下页内已被重排, 取最早可保证
        #  下一页严格更旧 → 不重复展示已见条目。)
        oldest = min(items, key=lambda it: it.ingested_at or it.published_at) if items else None
        next_cursor = encode_cursor(oldest) if (next_cursor_raw and oldest) else None

        # DEV-0176 T0.4 + DEV-0182 + DEV-0315: 三因子复合稳定重排 (只升降不删)。
        # 非 balanced 路径在此重排 (balanced 已在候选池切片前排过 — 此处为稳定幂等重排)。
        items = _rank_items(
            items,
            practice_multiplier=practice_multiplier,
            boost_set=boost_set, cat_prefs=cat_prefs, src_prefs=src_prefs,
        )
        item_dicts = [item.model_dump(mode="json") for item in items]
        if item_dicts:
            from backend.services.auto_classifier import classify_practice_domain

            for d in item_dicts:
                d["practice_domain"] = classify_practice_domain([], title=d.get("title") or "")

        # Phase 40: StatsPanel/TopNav 跟随当前 time_range (与 Grid 口径一致)
        cat_counts = self.count_by_category(tr)

        # Phase 42 修复: total 用去重 url 数, 与 items 口径一致
        # 之前用 count_in_range 返回行数 (同 url 多次入库会算多次),
        # 导致 "X / 841" 而 X 远小于 841, 分页器提前显示 "已是最后一页"
        cat_for_count = None if category == "all" else category
        true_total = _hrepo.count_unique_urls_in_range(
            tr, category=cat_for_count, keyword=keyword, exclude_category=exclude_category
        )

        # Phase 39: 最近一次采集的产出
        from backend.services.collection_service import get_latest_run as _get_latest_run
        latest = _get_latest_run()
        latest_iso = latest["at"].isoformat() if latest["at"] is not None else None

        result = {
            "version": API_VERSION,
            "items": item_dicts,
            "next_cursor": next_cursor,
            "total": true_total,  # 真实总数 (用于分页 "X / Y")
            "category": category,
            "time_range": tr.value,
            "keyword": keyword,
            "category_counts": cat_counts,  # 本周 (D7) — 与 Grid time_range 解耦
            # DEV-0176 T0.4: 本次加权所用的兴趣域 (前端徽标高亮用)
            "interest_domains": sorted(boost_set),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            # Phase 39: 新增 — 最近一轮 run_once() 的产出
            "latest_ingestion_count": int(latest["count"]),
            "latest_ingestion_at": latest_iso,
        }
        list_cache[cache_key] = result
        return result

    @staticmethod
    def _query_balanced(
        tr, limit: int, exclude_category: str | None = None,
        *, practice_multiplier: dict[str, float] | None = None,
        boost_set: set[str] | None = None,
        cat_prefs: dict[str, str] | None = None,
        src_prefs: dict[str, str] | None = None,
    ) -> tuple[list[HotspotItem], bool]:
        """分类均衡查询: 6 分类各取 N 条, 混合按 ingested_at DESC 排, **先 dedupe 再 take**。

        解决 security 排前挤掉其他 5 分类的问题。

        Phase 24: 用 ceil(limit/N) + min 5 保底, 即使 limit 很小也能保证每类至少
        5 条候选。bid 和 github 经常 0 条, 不影响其他分类配额。

        Phase 35: 移除 ``Category.TECH``(ai query 已合并 tech), 避免 tech 重复
        入桶导致均衡后 tech 条目翻倍挤掉其他分类。

        DEV-0175: ``exclude_category`` 命中的分类整桶跳过 (工作台聚焦裁决,
        前端默认排除 bid), 其余分类配额不变。

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
            Category.AI_SECURITY,
            Category.SECURITY,
            Category.FINANCE,
            Category.STARTUP,
            Category.GITHUB,
        ):
            if exclude_category and cat.value == exclude_category:
                continue
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
        # DEV-0315: 仅当用户**显式设了内容偏好**才在切片前重排候选池 ——
        # 这样"降权类目被挤出首页"才有真实效果; 无偏好时保持 DEV-0176 原语义
        # (时序切片 + 页内重排), 翻页游标连续性不受影响 (既有契约不变)。
        if cat_prefs or src_prefs:
            merged = _rank_items(
                merged,
                practice_multiplier=practice_multiplier,
                boost_set=boost_set or set(),
                cat_prefs=cat_prefs or {},
                src_prefs=src_prefs or {},
            )
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
    def _to_repo_cursor(cursor: str | None) -> str | None:
        """把 base64 服务层 cursor → repo 的 ``<unix_ts>_<id>`` 格式。

        None / 空 → None; 无效 → 抛 ``InvalidParamException`` (HTTP 400)。
        """
        if not cursor:
            return None
        cursor_id, ts_iso = decode_cursor(cursor)  # 失败 → InvalidParamException
        try:
            # v0.5 M1-Task1: 保留微秒精度 (.6f 与 HotspotRepository
            # ._make_cursor 同格式)。int() 截断会在同一秒内的多条记录间
            # 丢失边界 — page2 永远查不到同秒的最后一条。
            ts_float = datetime.fromisoformat(ts_iso).timestamp()
        except (TypeError, ValueError) as e:
            raise InvalidParamException(
                f"invalid cursor timestamp: {ts_iso!r}"
            ) from e
        return f"{ts_float:.6f}_{cursor_id}"

    # ------------------------------------------------------------------
    def get_hotspot(self, id_: str) -> dict:
        """详情查询。"""
        cache_key = f"hotspots:detail:{id_}"
        if cache_key in detail_cache:
            return detail_cache[cache_key]

        item = _hrepo.get_by_id(id_)
        if item is None:
            raise NotFoundException(f"hotspot {id_!r} not found")

        # v1.7 Phase 1 验收 1: 详情页显示自动提取的标签
        from backend.repository.tags_repo import TagRepository
        try:
            tags = TagRepository().list_by_hotspot(id_)
            tag_payload = [
                {"id": t.id, "label": t.label, "type": t.type, "weight": t.weight}
                for t in tags
            ]
        except Exception as e:
            logger.warning(f"get_hotspot: load tags failed for {id_}: {e}")
            tag_payload = []

        result = {
            "version": API_VERSION,
            "item": item.model_dump(mode="json"),
            "tags": tag_payload,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        detail_cache[cache_key] = result
        return result

    # ------------------------------------------------------------------
    def list_by_tags(
        self,
        tag_ids: list[str],
        mode: str = "or",
        limit: int = DEFAULT_LIMIT,
    ) -> dict:
        """v1.7 Phase 1: 按标签 AND/OR 筛选热点。

        与 ``list_hotspots`` 不同, 本方法不走 balanced/缓存流程 (标签筛选是
        强过滤条件, 命中量小, 缓存收益低且 key 复杂)。仍走 ``_dedupe_by_url``
        保证与列表页去重口径一致。
        """
        limit = min(max(1, limit), self.MAX_LIMIT)
        items = _hrepo.list_by_tags(tag_ids, mode=mode, limit=limit)
        items = self._dedupe_by_url(items)
        return {
            "version": API_VERSION,
            "items": [item.model_dump(mode="json") for item in items],
            "next_cursor": None,
            "total": len(items),
            "tag_mode": mode,
            "tag_ids": tag_ids,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    def list_picked(self, days: int = 2, limit: int = 30) -> list[dict]:
        """精选视图 Top-N (2026-09-27 四模式 P2): pick_score DESC。

        pick_score 由 pick_service 每轮采集尾部落列, NULL (未入选) 不返回。
        api 层经本方法读 repo — api 严禁直接 import repository (硬规则)。
        """
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        return _hrepo.list_picked_since(since, limit)

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


__all__ = ["HotspotService", "decode_cursor", "encode_cursor"]
