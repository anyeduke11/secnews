"""v0.8 B3 — AgentMemoryService: HITL 反馈 + 记忆召回 + 偏好挖掘统一入口.

v2 = user_memory (v1, 见 ``backend/services/user_memory_service.py``)
+ feedback_log + preference_miner + recall (§7.5)。

分层:
- ``record_feedback`` / ``list_feedback`` — 反馈日志 CRUD (校验 run 存在)
- ``recall``        — 委托 :class:`~backend.services.agent_memory.recall.MemoryRecall`
- ``mine_preferences`` — 委托 :class:`~backend.services.agent_memory.miner.PreferenceMiner`
- ``active_preferences`` — 读回当前生效偏好 (下次执行注入的数据源)

依赖方向: memory.py 顶层只依赖 stdlib + repository; recall/miner 顶层
import 本模块的 dataclass → 为避免循环, 本模块在方法体内 lazy import
recall/miner (与 ``backend/api/__init__.py`` lazy import 协议同款)。
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.db import get_connection


@dataclass
class MemoryHit:
    """recall 单条召回结果.

    Attributes
    ----------
    skill_run_id : str
        命中的历史 run id。
    skill_id : str
        该 run 所属 skill。
    intent_excerpt : str
        历史 intent 摘要 (兜底 result 前缀), 截 120 字符。
    score : float
        该 run 的反馈均分 (feedback_log join; 无反馈为 0.0)。
    created_at : str
        run 创建时间。
    similarity : float
        相似度 (exact=1.0 / simhash=1-海明距离/64 / keyword=命中率)。
    match_path : str
        命中路径: ``exact`` / ``simhash`` / ``keyword``。
    """

    skill_run_id: str
    skill_id: str
    intent_excerpt: str
    score: float
    created_at: str
    similarity: float
    match_path: str


@dataclass
class Preference:
    """一条已挖掘的用户偏好 (agent_preferences 行的业务形态).

    kind ∈ {avoid_skill, prefer_runner, prefer_style};
    evidence 为触发证据摘要 dict (落库时 JSON 序列化)。
    """

    kind: str
    value: str
    evidence: dict[str, Any]


class AgentMemoryService:
    """v2 记忆服务: 反馈落库 → 召回历史 → 挖掘偏好 → 读回注入."""

    # ------------------------------------------------------------------
    # 反馈 (HITL)
    # ------------------------------------------------------------------
    def record_feedback(
        self,
        skill_run_id: str,
        skill_id: str,
        score: int,
        comment: str = "",
    ) -> dict[str, Any]:
        """记录用户对某次 skill run 的反馈.

        Parameters
        ----------
        skill_run_id : str
            必须存在于 ``skill_runs`` 表, 否则 :class:`ValueError`
            (反馈与运行历史联动, 拒绝孤儿反馈)。
        skill_id : str
            该 run 所属 skill (冗余存储, 供按 skill 维度挖掘/查询)。
        score : int
            1-5 整数评分, 越界抛 :class:`ValueError`。
        comment : str
            可选文字评论。

        Returns
        -------
        dict
            落库后的完整反馈行。
        """
        if not isinstance(score, int) or not 1 <= score <= 5:
            raise ValueError(f"score must be int in [1, 5], got {score!r}")
        conn = get_connection()
        try:
            run = conn.execute(
                "SELECT run_id FROM skill_runs WHERE run_id = ?",
                (skill_run_id,),
            ).fetchone()
            if run is None:
                raise ValueError(
                    f"skill_run_id {skill_run_id!r} not found in skill_runs"
                )
            cur = conn.execute(
                "INSERT INTO feedback_log(skill_run_id, skill_id, score, comment) "
                "VALUES (?, ?, ?, ?)",
                (skill_run_id, skill_id, score, comment),
            )
            row = conn.execute(
                "SELECT * FROM feedback_log WHERE id = ?",
                (cur.lastrowid,),
            ).fetchone()
            return dict(row) if row else {}
        except ValueError:
            raise
        except sqlite3.Error as e:
            logger.error(
                "agent_memory record_feedback failed",
                extra={"trace_id": "", "skill_run_id": skill_run_id, "error": str(e)},
            )
            raise InternalException(
                f"agent_memory record_feedback failed: {e}"
            ) from e

    def list_feedback(self, skill_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """按 skill_id 倒序列出反馈 (默认最近 50 条)."""
        rows = get_connection().execute(
            "SELECT * FROM feedback_log WHERE skill_id = ? "
            "ORDER BY created_at DESC, id DESC LIMIT ?",
            (skill_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # 召回
    # ------------------------------------------------------------------
    def recall(self, intent: str, k: int = 5) -> list[MemoryHit]:
        """基于 intent 召回相关 skill_run 历史 (三路混合, 见 recall.py)."""
        from backend.services.agent_memory.recall import MemoryRecall

        return MemoryRecall().search(intent, k=k)

    # ------------------------------------------------------------------
    # 偏好挖掘
    # ------------------------------------------------------------------
    def mine_preferences(self) -> list[Preference]:
        """从 feedback_log + skill_runs 挖偏好并幂等落 agent_preferences."""
        from backend.services.agent_memory.miner import PreferenceMiner

        return PreferenceMiner().mine()

    def active_preferences(self) -> list[Preference]:
        """读回当前全部生效偏好 (按创建时间倒序), 供下次执行注入."""
        rows = get_connection().execute(
            "SELECT kind, value, evidence FROM agent_preferences "
            "ORDER BY created_at DESC, id DESC"
        ).fetchall()
        prefs: list[Preference] = []
        for r in rows:
            try:
                evidence = json.loads(r["evidence"]) if r["evidence"] else {}
            except (TypeError, ValueError):
                evidence = {}
            if not isinstance(evidence, dict):
                evidence = {}
            prefs.append(
                Preference(kind=r["kind"], value=r["value"], evidence=evidence)
            )
        return prefs


__all__ = ["AgentMemoryService", "MemoryHit", "Preference"]
