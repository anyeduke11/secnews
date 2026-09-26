"""KL 触发器 wiki_events 留痕 — kl_transition 统一写点 (治理 T4 review fix)。

生产复活链 (T1-T4 触发器) 此前不写 ``kl_transition`` — 该事件只有
kl_queue drain 发出, 于是吞吐视图 / 停摆判定
(``wiki_stats_service.kl_transition_throughput``) 对生产链恒 0 / 无心跳,
停摆黄条永久误报。本 helper 让触发器推进与 drain 同事件语义:
``kind='kl_transition'``, ``payload.stage`` = **到达阶段**。
"""
from __future__ import annotations

from backend.logging_config import logger


def log_stage_transition(trigger: str, item_id: str, stage: str) -> None:
    """触发器推进留痕 kl_transition。失败不阻塞推进 (与 engine._log_event 同哲学)。"""
    try:
        from backend.repository.wiki_event_repo import wiki_event_repo

        wiki_event_repo.log(
            kind="kl_transition",
            wiki_path=f"items/{item_id}.md",
            db_table="knowledge_items",
            db_row_id=item_id,
            agent=f"trigger:{trigger}",
            payload={"stage": stage, "trigger": trigger},
        )
    except Exception as exc:
        logger.warning(
            "kl_transition log failed (%s %s -> %s): %s",
            trigger, item_id, stage, exc,
        )
