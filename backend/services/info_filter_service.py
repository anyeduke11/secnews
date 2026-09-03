"""info_filter_service — 独立资讯筛选门禁服务 (v0.8 P1)

定位:
- 与 recency_gate / quality_gate 平行, 都是 source 侧过滤
- 不同点: recency/quality 是 item 评估, info_filter 是 **collector 启动前**
  的源级 allow/deny 名单
- 用户通过前端 /secnews/settings/info-filter 一键启停, 增删规则

数据模型 (migration 090):
- info_filter_rules 表: rule_type (allow/deny) × match_kind (category /
  source_name / source_id / tag) × match_value × enabled
- 默认空 (全 allow, 不限制)
- 与 feature_gate.info_filter 配合: 关 gate 时 collector 不查表 (零开销)

应用层 (Layer 1/2/3 见 backend.services.info_filter_gate):
- Layer 1: collect 入口 deny 命中 → skip 整源
- Layer 2: item_builder 落库前 deny 命中 → drop item
- Layer 3: ai_hub 拼 prompt 前 deny 命中 → 0 token 消耗

为什么不让前端直接控制:
- allow/deny 规则影响 crawler_runs 写入 + hotspot 落库, 必须有审计入口
- 服务层在规则 CRUD 时校验 match_kind 与 match_value 的合法性
  (e.g. source_id 必须是 "category:source_name" 格式, 否则前端写错
  无声失败)
"""
from __future__ import annotations

import sqlite3
from typing import Literal, Optional

from backend.logging_config import logger

RuleType = Literal["allow", "deny"]
MatchKind = Literal["category", "source_name", "source_id", "tag"]
_ALLOWED_RULE_TYPES = ("allow", "deny")
_ALLOWED_MATCH_KINDS = ("category", "source_name", "source_id", "tag")
_VALID_CATEGORIES = {
    "ai", "security", "finance", "tech", "github",
    "startup", "ai_security",
}


class InfoFilterError(ValueError):
    """info_filter 规则校验失败 / 操作错误。"""


def _validate(rule_type: str, match_kind: str, match_value: str) -> None:
    """校验 rule_type / match_kind / match_value 三元组合法性.

    - rule_type ∈ {allow, deny}
    - match_kind ∈ {category, source_name, source_id, tag}
    - match_value 非空
    - match_kind=category 时, match_value 必须在已知分类中 (防拼写错误)
    - match_kind=source_id 时, 必须是 "category:source_name" 格式
    """
    if rule_type not in _ALLOWED_RULE_TYPES:
        raise InfoFilterError(
            f"rule_type {rule_type!r} not in {_ALLOWED_RULE_TYPES}"
        )
    if match_kind not in _ALLOWED_MATCH_KINDS:
        raise InfoFilterError(
            f"match_kind {match_kind!r} not in {_ALLOWED_MATCH_KINDS}"
        )
    if not match_value or not match_value.strip():
        raise InfoFilterError("match_value must be non-empty")
    if match_kind == "category" and match_value not in _VALID_CATEGORIES:
        raise InfoFilterError(
            f"match_kind=category requires match_value in "
            f"{sorted(_VALID_CATEGORIES)}, got {match_value!r}"
        )
    if match_kind == "source_id":
        # source_id 格式: "category:source_name" (e.g. "finance:华尔街见闻")
        if ":" not in match_value:
            raise InfoFilterError(
                "match_kind=source_id requires format "
                "'category:source_name' (with colon), got "
                f"{match_value!r}"
            )
        cat, _ = match_value.split(":", 1)
        if cat not in _VALID_CATEGORIES:
            raise InfoFilterError(
                f"source_id category part {cat!r} not in "
                f"{sorted(_VALID_CATEGORIES)}"
            )


def list_rules(
    conn: sqlite3.Connection,
    enabled_only: bool = False,
) -> list[dict]:
    """列出全部规则 (含 disabled). 顺序: rule_type DESC (deny 先), id ASC."""
    sql = (
        "SELECT id, rule_type, match_kind, match_value, enabled, "
        "note, created_at, updated_at "
        "FROM info_filter_rules"
    )
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY CASE rule_type WHEN 'deny' THEN 0 ELSE 1 END, id ASC"
    rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]


def create_rule(
    conn: sqlite3.Connection,
    rule_type: str,
    match_kind: str,
    match_value: str,
    note: str = "",
    enabled: int = 1,
) -> int:
    """创建一条规则, 返回新 id. 校验失败抛 InfoFilterError."""
    _validate(rule_type, match_kind, match_value)
    cur = conn.execute(
        "INSERT INTO info_filter_rules "
        "(rule_type, match_kind, match_value, enabled, note) "
        "VALUES (?, ?, ?, ?, ?)",
        (rule_type, match_kind, match_value.strip(),
         1 if enabled else 0, note),
    )
    conn.commit()
    new_id = cur.lastrowid
    logger.info(
        f"info_filter: created rule id={new_id} "
        f"{rule_type}/{match_kind}/{match_value!r}"
    )
    return new_id


def update_rule(
    conn: sqlite3.Connection,
    rule_id: int,
    *,
    rule_type: Optional[str] = None,
    match_kind: Optional[str] = None,
    match_value: Optional[str] = None,
    note: Optional[str] = None,
    enabled: Optional[int] = None,
) -> bool:
    """更新一条规则. 至少传一个 kwarg. 返回是否真改了行.

    校验: 当改 rule_type / match_kind / match_value 之一时, 必须三者都校验
    (用现有行的另外两个字段补齐, 因为 schema 整体合法才能存).
    """
    if rule_id is None:
        raise InfoFilterError("rule_id is required")
    existing = conn.execute(
        "SELECT rule_type, match_kind, match_value, enabled, note "
        "FROM info_filter_rules WHERE id = ?",
        (rule_id,),
    ).fetchone()
    if existing is None:
        raise InfoFilterError(f"rule id={rule_id} not found")
    new_rt = rule_type if rule_type is not None else existing["rule_type"]
    new_mk = match_kind if match_kind is not None else existing["match_kind"]
    new_mv = match_value if match_value is not None else existing["match_value"]
    new_en = enabled if enabled is not None else existing["enabled"]
    new_note = note if note is not None else existing["note"]
    _validate(new_rt, new_mk, new_mv)
    cur = conn.execute(
        "UPDATE info_filter_rules "
        "SET rule_type = ?, match_kind = ?, match_value = ?, "
        "enabled = ?, note = ?, updated_at = datetime('now', 'localtime') "
        "WHERE id = ?",
        (new_rt, new_mk, new_mv.strip(),
         1 if new_en else 0, new_note, rule_id),
    )
    conn.commit()
    changed = cur.rowcount > 0
    if changed:
        logger.info(f"info_filter: updated rule id={rule_id}")
    return changed


def delete_rule(conn: sqlite3.Connection, rule_id: int) -> bool:
    """删除一条规则. 返回是否真删了行."""
    cur = conn.execute(
        "DELETE FROM info_filter_rules WHERE id = ?",
        (rule_id,),
    )
    conn.commit()
    changed = cur.rowcount > 0
    if changed:
        logger.info(f"info_filter: deleted rule id={rule_id}")
    return changed


def _matches(rule: dict, *, category: str, source_name: str,
             source_id: Optional[str] = None,
             tag: Optional[str] = None) -> bool:
    """判断一条规则是否命中给定的 (category, source_name, source_id, tag)."""
    mk, mv = rule["match_kind"], rule["match_value"]
    if mk == "category":
        return category == mv
    if mk == "source_name":
        return source_name == mv
    if mk == "source_id":
        # rule.match_value 格式 "category:source_name"
        if source_id is None:
            source_id = f"{category}:{source_name}"
        return source_id == mv
    if mk == "tag":
        return tag is not None and tag == mv
    return False  # 不应到达


def evaluate(
    rules: list[dict],
    *,
    category: str,
    source_name: str,
    source_id: Optional[str] = None,
    tag: Optional[str] = None,
) -> tuple[str, Optional[dict]]:
    """对给定的源/项评估规则集, 返回 (verdict, matched_rule).

    verdict ∈ {"allow", "deny", "neutral"}:
    - deny:  命中 deny 规则 → 拒绝
    - allow: 命中 allow 规则 → 强制放行
    - neutral: 没有 deny/allow 命中 → 走默认 (allow)

    评估顺序: 先扫全部 deny, 再扫全部 allow. deny 优先.
    这是"deny 默认赢, allow 是显式提升"语义 — 与多数 ACL (firewall)
    设计一致.

    rules 应当是 list_rules(enabled_only=True) 的结果 (调用方过滤).
    """
    matched_deny: Optional[dict] = None
    matched_allow: Optional[dict] = None
    for r in rules:
        if not r.get("enabled"):
            continue
        if not _matches(r, category=category, source_name=source_name,
                        source_id=source_id, tag=tag):
            continue
        if r["rule_type"] == "deny":
            if matched_deny is None:
                matched_deny = r
        elif r["rule_type"] == "allow":
            if matched_allow is None:
                matched_allow = r
    if matched_deny is not None:
        return "deny", matched_deny
    if matched_allow is not None:
        return "allow", matched_allow
    return "neutral", None


__all__ = [
    "InfoFilterError",
    "list_rules",
    "create_rule",
    "update_rule",
    "delete_rule",
    "evaluate",
]
