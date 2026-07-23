"""v1.7 Phase 1 — SAG (Signal-Amplify-Generate) 生命周期服务。

SAG 生命周期状态机 (PRD §3.3):
    signal → amplify:tagged → amplify:linked → amplify:complete → generate

本模块只实现 Phase 1 所需的最小能力:
- ``transition``: 把知识条目推进到指定 lifecycle 状态 (校验状态合法性 +
  单调前进), 同步回写 SQLite 与 ``knowledge/items/{id}.md``。
- ``promote_favorite_to_knowledge``: 收藏文章时, 以 url 派生 id 创建一条
  ``lifecycle='signal'`` 的知识条目 (已存在则直接返回 id, 不覆盖)。

设计
----
- .md 文件是 source of truth; SQLite 是读缓存。两处都写, .md 写失败仅告警
  不阻塞 (与 ``knowledge_sync`` 既有约定一致)。
- 状态推进允许跳跃 (如 signal → generate 直接归档合法), 但不允许回退到
  更早的状态 (避免数据倒流)。
"""
from __future__ import annotations

import logging

from backend.domain.knowledge_models import VALID_LIFECYCLE_STATES, KnowledgeItem, now_iso
from backend.repository.knowledge_repo import knowledge_repo

log = logging.getLogger("hotspot.sag")

# lifecycle 状态顺序 (用于单调性校验)
_STATE_ORDER = {
    "signal": 0,
    "amplify:tagged": 1,
    "amplify:linked": 2,
    "amplify:complete": 3,
    "generate": 4,
}


def transition(item_id: str, to_state: str) -> bool:
    """把知识条目 ``item_id`` 的 lifecycle 推进到 ``to_state``。

    规则:
    - ``to_state`` 必须是合法状态, 否则返回 False。
    - 条目不存在返回 False。
    - 不允许回退 (to_state 顺序 < 当前状态顺序) → 返回 False。
    - 相同状态 → 视为成功 (幂等) 返回 True。
    成功时同步写 SQLite + .md, 返回 True。
    """
    if to_state not in VALID_LIFECYCLE_STATES:
        log.warning(f"invalid lifecycle state: {to_state!r}")
        return False

    item = knowledge_repo.get_item(item_id)
    if item is None:
        log.warning(f"transition: item {item_id!r} not found")
        return False

    cur_order = _STATE_ORDER.get(item.lifecycle, 0)
    new_order = _STATE_ORDER[to_state]
    if new_order < cur_order:
        log.info(
            f"transition rejected (would regress): {item_id} "
            f"{item.lifecycle} -> {to_state}"
        )
        return False

    item.lifecycle = to_state
    item.updated_at = now_iso()
    knowledge_repo.upsert_item(item)

    # 回写 .md (非关键, 失败仅告警)
    try:
        from backend.services.knowledge_sync import write_item_to_md
        write_item_to_md(item.to_dict())
    except Exception as e:
        log.warning(f"write_item_to_md failed for {item_id} (non-critical): {e}")

    return True


def promote_favorite_to_knowledge(title: str, url: str) -> str:
    """收藏文章 → 创建 lifecycle='signal' 的知识条目。

    - id 由 url 派生 (``item_id_from_url``), 保证同 url 幂等。
    - 已存在则直接返回 id (不覆盖已有 lifecycle/tags)。
    - 同时写 SQLite + ``knowledge/items/{id}.md``。
    返回 item_id。
    """
    from backend.services.data_cleaning import item_id_from_url

    item_id = item_id_from_url(url)
    if knowledge_repo.get_item(item_id) is not None:
        log.debug(f"promote: item {item_id} already exists, skip")
        return item_id

    item = KnowledgeItem(
        id=item_id,
        title=title or "Untitled",
        source="secnews",
        source_url=url,
        lifecycle="signal",
        ingested_at=now_iso(),
        updated_at=now_iso(),
    )
    knowledge_repo.upsert_item(item)

    try:
        from backend.services.knowledge_sync import write_item_to_md
        write_item_to_md(item.to_dict())
    except Exception as e:
        log.warning(f"write_item_to_md failed for {item_id} (non-critical): {e}")

    log.info(f"promote: created knowledge item {item_id} from favorite")
    return item_id


__all__ = ["transition", "promote_favorite_to_knowledge"]
