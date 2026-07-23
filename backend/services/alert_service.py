"""v1.7 Phase 3 — 告警服务: 规则匹配 + cooldown + SSE 触发.

核心功能:
1. evaluate_condition(condition, hotspot) — 条件评估器
   - type=tag_match: 检查热点标签是否匹配 (AND/OR + contains_any)
   - type=category_match: 检查热点 category
   - type=keyword_match: 检查标题/摘要关键词
2. evaluate_hotspot(hotspot_id) — 对热点跑全部启用规则, 触发告警
   - cooldown 检查: 同一规则在 cooldown_sec 内不重复触发
   - 触发: 写入 alerts 表 + publish_event SSE 推送
3. _fire(rule, hotspot) — 单条规则触发 (写库 + SSE)

设计决策:
- 标签来源: hotspots.tags (JSON 数组) + hotspot_tags 关联表 (双重取, 取并集)
  plan 代码片段只读 hotspots.tags, 但 v1.7 Phase 1 已迁到 hotspot_tags 表,
  这里以 hotspot_tags 关联表为准 (source of truth), 兼容 hotspots.tags 缓存.
- cooldown: 用 alert_rules.last_fired_at + cooldown_sec 判断,
  不用 alerts 表 (避免误判已删除的告警).
- SSE 推送: 复用 events.publish_event, event_type="alert".
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from backend.repository.alerts_repo import AlertRepository, AlertRuleRepository
from backend.repository.db import get_connection

logger = logging.getLogger("hotspot.alert")


# ---------------------------------------------------------------------------
# 条件评估器
# ---------------------------------------------------------------------------
def evaluate_condition(condition: dict, hotspot: dict) -> bool:
    """评估单条 condition 是否匹配热点.

    Args:
        condition: 规则条件 dict, 必须含 "type"
            - type=tag_match: {type, operator:AND|OR, conditions: [{op:contains_any, value:[tag_ids]}]}
            - type=category_match: {type, value: ["ai", "security"]}
            - type=keyword_match: {type, value: ["关键词1", "关键词2"], field: title|summary|both}
        hotspot: 热点 dict, 至少含 title/summary/category/tags
            tags 可以是 list[str] 或 JSON 字符串

    Returns:
        bool: 是否匹配
    """
    ctype = condition.get("type")
    if ctype == "tag_match":
        return _eval_tag_match(condition, hotspot)
    if ctype == "category_match":
        return _eval_category_match(condition, hotspot)
    if ctype == "keyword_match":
        return _eval_keyword_match(condition, hotspot)
    logger.warning(f"unknown condition type: {ctype}")
    return False


def _get_hotspot_tags(hotspot: dict) -> set[str]:
    """从 hotspot dict 提取标签集合 (兼容 list / JSON 字符串)."""
    tags_raw = hotspot.get("tags")
    if tags_raw is None:
        return set()
    if isinstance(tags_raw, str):
        try:
            tags_raw = json.loads(tags_raw)
        except (TypeError, ValueError):
            return set()
    if isinstance(tags_raw, list):
        return {str(t) for t in tags_raw}
    return set()


def _eval_tag_match(condition: dict, hotspot: dict) -> bool:
    """标签匹配: operator AND/OR + 子条件 contains_any."""
    tags = _get_hotspot_tags(hotspot)
    if not tags:
        return False
    op = condition.get("operator", "OR").upper()
    subs = condition.get("conditions", [])
    if not subs:
        return False
    if op == "AND":
        return all(_match_sub(c, tags) for c in subs)
    return any(_match_sub(c, tags) for c in subs)


def _match_sub(c: dict, tags: set[str]) -> bool:
    """子条件匹配: op=contains_any → tags 与 value 有交集."""
    op = c.get("op", "contains_any")
    vals = set(c.get("value", []))
    if op == "contains_any":
        return bool(tags & vals)
    if op == "contains_all":
        return vals.issubset(tags)
    if op == "contains_none":
        return not (tags & vals)
    return False


def _eval_category_match(condition: dict, hotspot: dict) -> bool:
    """category 匹配: hotspot.category in condition.value."""
    cat = hotspot.get("category")
    if cat is None:
        return False
    # category 可能是 Category enum 或 str
    cat_str = cat.value if hasattr(cat, "value") else str(cat)
    vals = condition.get("value", [])
    return cat_str in vals


def _eval_keyword_match(condition: dict, hotspot: dict) -> bool:
    """关键词匹配: 检查 title/summary 包含任一关键词."""
    field = condition.get("field", "both")
    keywords = condition.get("value", [])
    title = (hotspot.get("title") or "").lower()
    summary = (hotspot.get("summary") or "").lower()
    for kw in keywords:
        kw_l = str(kw).lower()
        if not kw_l:
            continue
        if field in ("title", "both") and kw_l in title:
            return True
        if field in ("summary", "both") and kw_l in summary:
            return True
    return False


# ---------------------------------------------------------------------------
# cooldown 检查
# ---------------------------------------------------------------------------
def _cooldown_ready(rule: dict, now: Optional[datetime] = None) -> bool:
    """检查规则是否已过 cooldown 期 (可再次触发).

    Args:
        rule: 规则 dict, 含 last_fired_at / cooldown_sec
        now: 当前时间 (测试注入), 默认 utcnow
    Returns:
        True = 可触发, False = 冷却中
    """
    last_fired = rule.get("last_fired_at")
    if not last_fired:
        return True
    try:
        last_dt = datetime.fromisoformat(last_fired.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True
    now = now or datetime.now(timezone.utc)
    cooldown_sec = int(rule.get("cooldown_sec") or 3600)
    elapsed = (now - last_dt).total_seconds()
    return elapsed >= cooldown_sec


# ---------------------------------------------------------------------------
# 规则触发
# ---------------------------------------------------------------------------
def _fire(rule: dict, hotspot: dict) -> dict:
    """触发单条规则: 写入 alerts 表 + SSE 推送.

    Returns:
        新建的 alert dict
    """
    rule_id = rule["id"]
    entity_type = "hotspot"
    entity_id = str(hotspot.get("id") or "")
    payload = {
        "rule_name": rule.get("name"),
        "rule_id": rule_id,
        "title": hotspot.get("title"),
        "summary": hotspot.get("summary"),
        "category": str(hotspot.get("category")),
        "url": str(hotspot.get("url") or ""),
    }
    alert = AlertRepository().add(
        rule_id=rule_id,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
    )
    # 更新规则 last_fired_at (供后续 cooldown 检查)
    AlertRuleRepository().touch_last_fired(rule_id)

    # SSE 推送 (best-effort, 失败不影响告警写入)
    try:
        from backend.api.events import publish_event
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            loop.create_task(publish_event("alert", {"alert": alert}))
        else:
            # 同步上下文 (测试/CLI): 直接调度
            asyncio.run(publish_event("alert", {"alert": alert}))
    except Exception as e:
        logger.warning(f"SSE publish failed (alert {alert['id']}): {e}")

    return alert


# ---------------------------------------------------------------------------
# 入口: 评估热点
# ---------------------------------------------------------------------------
def evaluate_hotspot(hotspot_id: str) -> list[str]:
    """对指定热点跑全部启用规则, 触发匹配的告警.

    Args:
        hotspot_id: hotspots.id
    Returns:
        触发的 rule_id 列表
    """
    hotspot = _load_hotspot(hotspot_id)
    if not hotspot:
        return []

    rules = AlertRuleRepository().list_enabled()
    fired: list[str] = []
    for rule in rules:
        if not _cooldown_ready(rule):
            continue
        condition = rule["condition"]
        if not isinstance(condition, dict):
            # condition 已被 repo 反序列化为 dict, 防御性处理
            continue
        if evaluate_condition(condition, hotspot):
            _fire(rule, hotspot)
            fired.append(rule["id"])
    return fired


def _load_hotspot(hotspot_id: str) -> Optional[dict]:
    """加载热点 + 关联标签, 返回 dict (含 tags 列表).

    优先从 hotspots 表读取 (含 title/summary/category),
    标签从 hotspot_tags 关联表读取 (Phase 1 source of truth),
    兼容 hotspots.tags 缓存列.
    """
    from backend.repository.hotspot_repo import HotspotRepository
    from backend.repository.tags_repo import TagRepository

    item = HotspotRepository().get_by_id(hotspot_id)
    if item is None:
        return None

    # 从关联表读标签 (source of truth)
    tags = [t.id for t in TagRepository().list_by_hotspot(hotspot_id)]
    # 兼容: 若关联表为空, 退回 hotspots.tags 缓存列
    if not tags:
        row = get_connection().execute(
            "SELECT tags FROM hotspots WHERE id = ?", (hotspot_id,)
        ).fetchone()
        if row and row["tags"]:
            try:
                tags = json.loads(row["tags"])
            except (TypeError, ValueError):
                tags = []

    return {
        "id": item.id,
        "title": item.title,
        "summary": item.summary,
        "category": item.category,
        "url": str(item.url) if item.url else "",
        "tags": tags,
    }
