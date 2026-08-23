"""v1.7 Phase 1 — SAG 生命周期服务 (P1-3: 已适配 KL 五阶段)。

P1-3 (2026-08-15): 生命周期统一为 KL 五阶段规范 (kl:raw/refine/link/
structure/publish)。本模块保留 SAG 语义 (信号→放大→生成) 但改用 KL 值:
- ``promote_favorite_to_knowledge`` 创建 ``lifecycle='kl:raw'``
- ``transition`` 推进 kl:* 状态, 兼容接受 legacy SAG 值 (映射到对应 kl:*)

设计
----
- .md 文件是 source of truth; SQLite 是可重建的读索引。**先写 .md 且必须
  成功** (失败则整个操作失败, 不产生 DB 领先于 md 的分歧); DB 写入紧随
  其后, DB 写入失败由下次 full_sync 从 md 自动补齐。
- 状态推进允许跳跃 (如 kl:raw → kl:publish 直接归档合法), 但不允许回退到
  更早的状态 (避免数据倒流)。
"""
from __future__ import annotations

import logging

from backend.domain.knowledge_models import (
    VALID_LIFECYCLE_STATES,
    KnowledgeItem,
    normalize_lifecycle,
    now_iso,
)
from backend.repository.knowledge_repo import knowledge_repo

log = logging.getLogger("hotspot.sag")

# lifecycle 状态顺序 (P1-3: KL 五阶段规范; legacy SAG 值映射同序)
_STATE_ORDER = {
    "kl:raw": 0,
    "kl:refine": 1,
    "kl:link": 2,
    "kl:structure": 3,
    "kl:publish": 4,
    # legacy 兼容 (映射到对应 KL 位置, 防止历史值回退判断错乱)
    "signal": 0,
    "amplify:tagged": 1,
    "amplify:linked": 2,
    "amplify:complete": 3,
    "generate": 4,
}


def transition(item_id: str, to_state: str) -> bool:
    """把知识条目 ``item_id`` 的 lifecycle 推进到 ``to_state``。

    规则:
    - ``to_state`` 必须是合法状态 (kl:* 或 legacy SAG), 否则返回 False。
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

    # P1-3: 统一落库为 KL 规范值
    item.lifecycle = normalize_lifecycle(to_state)
    item.updated_at = now_iso()

    # P0.4: lifecycle 是中间状态, 只更新 DB, 不回写 md
    # (md 只由用户编辑/编译器/T4 发布器写, 自动状态转换不回写)
    knowledge_repo.upsert_item(item)
    return True


def promote_favorite_to_knowledge(title: str, url: str) -> str:
    """收藏文章 → 创建 lifecycle='kl:raw' 的知识条目 (P1-3 统一为 KL 规范).

    - id 由 url 派生 (``item_id_from_url``), 保证同 url 幂等。
    - 已存在则直接返回 id (不覆盖已有 lifecycle/tags)。
    - md 是真相源: 先写 ``knowledge/items/{id}.md`` (失败则抛错, 由调用方
      兜底), 再写 SQLite 索引。
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
        lifecycle="kl:raw",
        ingested_at=now_iso(),
        updated_at=now_iso(),
    )

    # md 先写且必须成功 (真相源); 失败直接抛出, 调用方 (favorites API)
    # 已有 try/except 非关键兜底。
    from backend.services import ai_hub
    ai_hub.write_item(item.to_dict(), agent="api:promote_favorite")

    knowledge_repo.upsert_item(item)

    log.info(f"promote: created knowledge item {item_id} from favorite")
    return item_id


__all__ = ["promote_favorite_to_knowledge", "transition"]
