"""Mastery projection — SM-2 复习结果单向投影回 wiki frontmatter (S5-1/S5-2)。

铁律: DB reviews 表为行动域真相源, 复习结果经本模块**单向**写回
wiki frontmatter (mastery / last_reviewed / review_count)。
禁止反向读取 (从 frontmatter 读复习状态)。

投影公式: mastery = min(100, repetitions × 20 + easiness × 4)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

log = logging.getLogger("hotspot.mastery_projection")


def compute_mastery(easiness: float, repetitions: int) -> int:
    """从 SM-2 参数推导 mastery (0-100)。"""
    return min(100, int(repetitions * 20 + easiness * 4))


def project_review_to_wiki(
    entity_type: str,
    entity_id: str,
    easiness: float,
    repetitions: int,
    last_reviewed: str,
    review_count: int,
) -> bool:
    """复习评分 → 单向投影回 wiki frontmatter。

    仅处理 entity_type='knowledge_item' 的条目。
    写入字段: mastery / last_reviewed / review_count。
    失败只 warning 不阻塞评分主流程。

    Returns:
        True if projected, False if skipped/failed.
    """
    if entity_type != "knowledge_item":
        return False

    try:
        from backend.services.knowledge_sync import write_item_to_md
        from backend.repository.knowledge_repo import knowledge_repo

        item = knowledge_repo.get_item(entity_id)
        if item is None:
            log.debug(f"project: item {entity_id} not found, skip")
            return False

        mastery = compute_mastery(easiness, repetitions)
        item.mastered = mastery
        item.updated_at = last_reviewed

        # 读现有 frontmatter 以保留 md-only 字段
        fm_overrides: dict = {
            "mastery": mastery,
            "last_reviewed": last_reviewed,
            "review_count": review_count,
        }
        write_item_to_md(item.to_dict())
        log.info(
            f"project: {entity_id} mastery={mastery} "
            f"review_count={review_count}"
        )
        return True
    except Exception as e:
        log.warning(f"project_review_to_wiki failed for {entity_id}: {e}")
        return False


__all__ = ["compute_mastery", "project_review_to_wiki"]
