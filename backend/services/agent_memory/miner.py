"""v0.8 B3 — 偏好挖掘: 从 skill_runs + feedback_log 规则化挖出 agent_preferences.

三条规则 (阈值与 docs/V0.8_REFACTOR_PLAN.md §7.5 一致):
1. ``avoid_skill``   — 同 skill_id 的 run status='failed' ≥3 次
2. ``prefer_runner`` — 同 runner 成功 ≥5 次 (runner 从 skill_runs.metrics
   JSON 的 ``runner`` 键提取, 缺失则跳过该规则)
3. ``prefer_style``  — 同 skill_id 反馈 score≥4 出现 ≥3 次
   (value = 该 skill 历史意图/评论的关键词摘要)

产出 upsert ``agent_preferences``: UNIQUE(kind, value) 已存在即跳过
(``ON CONFLICT DO NOTHING``), 重复 mine 幂等。
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.db import get_connection
from backend.services.agent_memory.memory import Preference
from backend.services.agent_memory.recall import extract_intent, top_keywords

AVOID_SKILL_FAIL_THRESHOLD = 3
PREFER_RUNNER_SUCCESS_THRESHOLD = 5
PREFER_STYLE_SCORE_THRESHOLD = 4
PREFER_STYLE_COUNT_THRESHOLD = 3

# 成功态词表: skill_runs 尚无统一 writer (B 批次并行落地),
# 同时接受 trigger_tickets 词表 ('done') 与直译词表 ('success') 防漏。
_SUCCESS_STATUSES = ("done", "success")


class PreferenceMiner:
    """规则化偏好挖掘器 (无状态, 每次 mine() 全量扫描当前证据)."""

    def mine(self) -> list[Preference]:
        """扫描 skill_runs + feedback_log, 挖出偏好并幂等落 agent_preferences.

        Returns
        -------
        list[Preference]
            本次规则触发出的全部偏好 (含已存在被跳过的 — 表行数不增,
            证据以本次扫描为准)。
        """
        try:
            prefs = self._mine_avoid_skill()
            prefs += self._mine_prefer_runner()
            prefs += self._mine_prefer_style()
            for pref in prefs:
                self._insert_if_absent(pref)
        except sqlite3.Error as e:
            logger.error(
                "agent_memory mine_preferences failed",
                extra={"trace_id": "", "error": str(e)},
            )
            raise InternalException(f"agent_memory mine_preferences failed: {e}") from e
        return prefs

    # ------------------------------------------------------------------
    # 规则 ①: 失败 ≥3 → avoid_skill
    # ------------------------------------------------------------------
    def _mine_avoid_skill(self) -> list[Preference]:
        """同 skill 失败次数达到阈值 → avoid_skill:<skill_id>."""
        rows = get_connection().execute(
            "SELECT skill_id, COUNT(*) AS failed FROM skill_runs "
            "WHERE status = 'failed' GROUP BY skill_id "
            "HAVING failed >= ?",
            (AVOID_SKILL_FAIL_THRESHOLD,),
        ).fetchall()
        return [
            Preference(
                kind="avoid_skill",
                value=r["skill_id"],
                evidence={
                    "rule": "failed_runs",
                    "failed_runs": r["failed"],
                    "threshold": AVOID_SKILL_FAIL_THRESHOLD,
                },
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # 规则 ②: 同 runner 成功 ≥5 → prefer_runner
    # ------------------------------------------------------------------
    def _mine_prefer_runner(self) -> list[Preference]:
        """从成功 run 的 metrics JSON 提取 runner, 成功 ≥5 → prefer_runner.

        metrics 缺失 / 非法 JSON / 无 runner 键的行直接跳过 (无证据不挖)。
        """
        rows = get_connection().execute(
            "SELECT run_id, metrics FROM skill_runs "
            f"WHERE status IN ({','.join('?' for _ in _SUCCESS_STATUSES)}) "
            "AND metrics IS NOT NULL",
            _SUCCESS_STATUSES,
        ).fetchall()
        success_by_runner: dict[str, list[str]] = {}
        for r in rows:
            runner = self._runner_from_metrics(r["metrics"])
            if runner:
                success_by_runner.setdefault(runner, []).append(r["run_id"])
        return [
            Preference(
                kind="prefer_runner",
                value=runner,
                evidence={
                    "rule": "runner_success",
                    "success_runs": len(run_ids),
                    "threshold": PREFER_RUNNER_SUCCESS_THRESHOLD,
                    "sample_run_ids": run_ids[:5],
                },
            )
            for runner, run_ids in sorted(success_by_runner.items())
            if len(run_ids) >= PREFER_RUNNER_SUCCESS_THRESHOLD
        ]

    @staticmethod
    def _runner_from_metrics(metrics_json: str | None) -> str:
        """解析 metrics JSON 里的 runner 名; 缺失 / 非法返回空串."""
        if not metrics_json:
            return ""
        try:
            data = json.loads(metrics_json)
        except (TypeError, ValueError):
            return ""
        if isinstance(data, dict):
            runner = data.get("runner")
            if isinstance(runner, str) and runner.strip():
                return runner.strip()
        return ""

    # ------------------------------------------------------------------
    # 规则 ③: score≥4 ×3 → prefer_style
    # ------------------------------------------------------------------
    def _mine_prefer_style(self) -> list[Preference]:
        """同 skill 高分反馈 (score≥4) ≥3 次 → prefer_style:<关键词摘要>.

        value 的关键词摘要取自该 skill 历史 run 的 intent 文本 + 反馈评论
        的 top-3 关键词; 全空时兜底 skill_id 本身, 保证 value 非空。
        """
        rows = get_connection().execute(
            "SELECT skill_id, COUNT(*) AS high FROM feedback_log "
            "WHERE score >= ? GROUP BY skill_id "
            "HAVING high >= ?",
            (PREFER_STYLE_SCORE_THRESHOLD, PREFER_STYLE_COUNT_THRESHOLD),
        ).fetchall()
        prefs: list[Preference] = []
        for r in rows:
            skill_id = r["skill_id"]
            texts = self._skill_texts(skill_id)
            keywords = top_keywords(texts, limit=3) or [skill_id]
            prefs.append(
                Preference(
                    kind="prefer_style",
                    value=" ".join(keywords),
                    evidence={
                        "rule": "high_score_feedback",
                        "skill_id": skill_id,
                        "high_score_count": r["high"],
                        "score_threshold": PREFER_STYLE_SCORE_THRESHOLD,
                        "count_threshold": PREFER_STYLE_COUNT_THRESHOLD,
                    },
                )
            )
        return prefs

    @staticmethod
    def _skill_texts(skill_id: str) -> list[str]:
        """收集该 skill 的全部 intent 文本 + 反馈评论 (关键词摘要原料)."""
        conn = get_connection()
        intents = [
            extract_intent(r["inputs"])
            for r in conn.execute(
                "SELECT inputs FROM skill_runs WHERE skill_id = ?",
                (skill_id,),
            ).fetchall()
        ]
        comments = [
            r["comment"]
            for r in conn.execute(
                "SELECT comment FROM feedback_log WHERE skill_id = ? "
                "AND comment IS NOT NULL",
                (skill_id,),
            ).fetchall()
        ]
        return [t for t in (*intents, *comments) if t]

    # ------------------------------------------------------------------
    # 落库 (幂等)
    # ------------------------------------------------------------------
    @staticmethod
    def _insert_if_absent(pref: Preference) -> None:
        """UNIQUE(kind, value) 冲突即跳过 — 重复 mine 不产生重复行."""
        get_connection().execute(
            "INSERT INTO agent_preferences(kind, value, evidence) "
            "VALUES (?, ?, ?) ON CONFLICT(kind, value) DO NOTHING",
            (pref.kind, pref.value, json.dumps(pref.evidence, ensure_ascii=False)),
        )


__all__ = [
    "AVOID_SKILL_FAIL_THRESHOLD",
    "PREFER_RUNNER_SUCCESS_THRESHOLD",
    "PREFER_STYLE_COUNT_THRESHOLD",
    "PREFER_STYLE_SCORE_THRESHOLD",
    "PreferenceMiner",
]
