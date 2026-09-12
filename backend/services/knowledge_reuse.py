"""Knowledge 复用/采用/召回块 — SK-05 复用派生 + C12 adoption + SK-06 复查 + 读时召回.

knowledge_service 拆分 (Batch 4 B) 的实现模块之一: adoption / outcome /
reuse receipt / recall / review-due / 全局只读查询, 以及模块级
auto_recall_for_case / add_agent_link (Batch 2 D 自 api 层下沉的 SQL)。
以 mixin 形式并入 KnowledgeService (knowledge_service.py facade),
公开 API 逐字不变。
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from backend.logging_config import logger
from backend.repository.db import get_connection
from backend.services.knowledge_common import (
    _VALID_KIND,
    _VALID_STATUS,
    KnowledgeConflictError,
    KnowledgeValidationError,
    _utcnow_iso,
)


class KnowledgeReuseMixin:
    """list / get / reuse (SK-05 派生) + C12 adoption + SK-06 复查扫描."""

    # ------------------------------------------------------------------
    # list / get / reuse (SK-05 派生)
    # ------------------------------------------------------------------
    def list_by_case(
        self, case_id: str, *, status: str | None = None, kind: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> dict[str, Any]:
        if status and status not in _VALID_STATUS:
            raise KnowledgeValidationError(f"invalid status: {status}")
        if kind and kind not in _VALID_KIND:
            raise KnowledgeValidationError(f"invalid kind: {kind}")
        items, total = self.repo.list_by_case(
            case_id, status=status, kind=kind, limit=limit, offset=offset,
        )
        return {"items": items, "total": total}

    def list_all(
        self, *, status: str | None = None, kind: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> dict[str, Any]:
        """T15.5 全局 list (KnowledgeView 走真实 listAll 替换 placeholder)."""
        if status and status not in _VALID_STATUS:
            raise KnowledgeValidationError(f"invalid status: {status}")
        if kind and kind not in _VALID_KIND:
            raise KnowledgeValidationError(f"invalid kind: {kind}")
        items, total = self.repo.list_all(
            status=status, kind=kind, limit=limit, offset=offset,
        )
        return {"items": items, "total": total}

    def get(self, knowledge_id: str) -> dict[str, Any]:
        return self._require(knowledge_id)

    def get_reuse_receipt(self, knowledge_id: str) -> dict[str, Any]:
        """C12 R16.5: ReuseReceipt 只数 adoptions, 弃用 by_judgment/by_action.

        Returns
        -------
        {
            "total": int,                       # 决策=adopted 计数
            "by_decision": {adopted, skipped, rejected},
            "by_outcome": {success, partial, failure, unknown},
            "recent_30d": int,                  # 30 天内 adoptions 数
        }
        """
        self._require(knowledge_id)
        conn = get_connection()
        # 决策分布
        decision_rows = conn.execute(
            "SELECT decision, COUNT(*) FROM v1_knowledge_adoptions "
            "WHERE knowledge_id = ? GROUP BY decision",
            (knowledge_id,),
        ).fetchall()
        by_decision: dict[str, int] = {}
        total = 0
        for dec, cnt in decision_rows:
            by_decision[dec] = cnt
            if dec == "adopted":
                total = cnt
        # 结果分布
        outcome_rows = conn.execute(
            "SELECT COALESCE(outcome,'unknown'), COUNT(*) FROM v1_knowledge_adoptions "
            "WHERE knowledge_id = ? AND decision = 'adopted' GROUP BY outcome",
            (knowledge_id,),
        ).fetchall()
        by_outcome: dict[str, int] = {}
        for out, cnt in outcome_rows:
            by_outcome[out] = cnt
        # 30 天内
        recent_30d_row = conn.execute(
            "SELECT COUNT(*) FROM v1_knowledge_adoptions "
            "WHERE knowledge_id = ? AND decision = 'adopted' "
            "AND adopted_at >= datetime('now', '-30 days')",
            (knowledge_id,),
        ).fetchone()
        recent_30d = int(recent_30d_row[0]) if recent_30d_row else 0
        return {
            "total": total,
            "by_decision": by_decision,
            "by_outcome": by_outcome,
            "recent_30d": recent_30d,
        }

    # ------------------------------------------------------------------
    # C12 R16 — knowledge adoption (derived_from vs adopted_by 物理分离)
    # ------------------------------------------------------------------
    def record_adoption(
        self,
        *,
        knowledge_id: str,
        case_id: str,
        condition_diff: list[dict[str, Any]],
        decision: str,
        decided_by: str,
        adopted_by: str | None = None,
    ) -> dict[str, Any]:
        """C12 R16.2: 记录一次知识采用 → 物理写 v1_knowledge_adoptions (新表).

        Parameters
        ----------
        knowledge_id :  采用的知识 id
        case_id      :  采用方 case (与原创建 case 可不同, 跨 case 复用)
        condition_diff: 与原 conditions/counter_examples 的差异 list
                       [{field, expected, actual, severity}, ...]
        decision     :  adopted|skipped|rejected
        decided_by   :  决策人 (who)
        adopted_by   :  默认 decided_by (保留双字段, audit 区分)

        Returns
        -------
        {id, knowledge_id, knowledge_revision, case_id, decision, ...}
        """
        if decision not in ("adopted", "skipped", "rejected"):
            raise KnowledgeValidationError(
                f"decision must be adopted|skipped|rejected, got {decision!r}"
            )
        k = self._require(knowledge_id)
        if k["status"] not in ("published", "deprecated"):
            raise KnowledgeConflictError(
                f"knowledge {knowledge_id} status={k['status']} "
                f"(adoption requires published/deprecated)"
            )
        # case 必存
        conn = get_connection()
        row = conn.execute("SELECT 1 FROM v1_cases WHERE id = ?", (case_id,)).fetchone()
        if row is None:
            raise KnowledgeValidationError(f"case {case_id} not found")
        now = _utcnow_iso()
        cur = conn.execute(
            "SELECT id, decision, condition_diff_json, outcome, outcome_note, "
            "adopted_at, adopted_by, decided_by FROM v1_knowledge_adoptions "
            "WHERE knowledge_id = ? AND knowledge_revision = ? AND case_id = ?",
            (knowledge_id, k["revision"], case_id),
        ).fetchone()
        if cur is not None:
            # 幂等: 已有 adoption 行, update decision + diff
            conn.execute(
                "UPDATE v1_knowledge_adoptions SET decision = ?, "
                "condition_diff_json = ?, decided_by = ?, adopted_by = ?, "
                "adopted_at = ? WHERE id = ?",
                (
                    decision,
                    json.dumps(condition_diff, ensure_ascii=False),
                    decided_by,
                    adopted_by or decided_by,
                    now,
                    cur[0],
                ),
            )
            conn.commit()
            return {
                "id": cur[0], "knowledge_id": knowledge_id,
                "knowledge_revision": k["revision"], "case_id": case_id,
                "decision": decision, "outcome": cur[3],
                "outcome_note": cur[4], "adopted_at": now,
                "adopted_by": adopted_by or decided_by, "decided_by": decided_by,
            }
        # 全新 adoption 行
        cur = conn.execute(
            "INSERT INTO v1_knowledge_adoptions (knowledge_id, knowledge_revision, "
            "case_id, decision, condition_diff_json, outcome, outcome_note, "
            "adopted_at, adopted_by, decided_by) "
            "VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?)",
            (
                knowledge_id, k["revision"], case_id, decision,
                json.dumps(condition_diff, ensure_ascii=False),
                now, adopted_by or decided_by, decided_by,
            ),
        )
        conn.commit()
        return {
            "id": cur.lastrowid, "knowledge_id": knowledge_id,
            "knowledge_revision": k["revision"], "case_id": case_id,
            "decision": decision, "outcome": None, "outcome_note": None,
            "adopted_at": now,
            "adopted_by": adopted_by or decided_by, "decided_by": decided_by,
        }

    def record_outcome(
        self,
        *,
        knowledge_id: str,
        case_id: str,
        outcome: str,
        outcome_note: str | None = None,
    ) -> dict[str, Any]:
        """C12 R16.6: 记录采用结果 (success|partial|failure).

        同一 case 多次 outcome 以最后一条为准 (append-only-ish: 走 UPDATE).
        outcome 不影响 total 计数 (只改 by_outcome 分布).
        """
        if outcome not in ("success", "partial", "failure"):
            raise KnowledgeValidationError(
                f"outcome must be success|partial|failure, got {outcome!r}"
            )
        self._require(knowledge_id)
        conn = get_connection()
        row = conn.execute(
            "SELECT id, knowledge_revision FROM v1_knowledge_adoptions "
            "WHERE knowledge_id = ? AND case_id = ? AND decision = 'adopted'",
            (knowledge_id, case_id),
        ).fetchone()
        if row is None:
            raise KnowledgeValidationError(
                f"no adopted row for knowledge {knowledge_id} case {case_id} "
                f"(record_adoption first)"
            )
        conn.execute(
            "UPDATE v1_knowledge_adoptions SET outcome = ?, outcome_note = ? "
            "WHERE id = ?",
            (outcome, outcome_note, row[0]),
        )
        conn.commit()
        return {
            "id": row[0], "knowledge_id": knowledge_id,
            "knowledge_revision": row[1], "case_id": case_id,
            "outcome": outcome, "outcome_note": outcome_note,
        }

    # ------------------------------------------------------------------
    # 只读查询 (Batch 2 D: api 层 SQL 下沉落点 — case_api / knowledge_api)
    # ------------------------------------------------------------------
    def case_reuse_summary(self, case_id: str) -> dict[str, Any]:
        """v0.8.5 D4: 复利卡 (诚实计数) — 本 case 的知识采用/回执汇总.

        只报真实记录数 (v1_knowledge_adoptions), 不做「节省 X 小时」类
        无基线估算。表缺失等异常显零值不阻断聚合 (与原 api 行为一致)。
        """
        try:
            conn = get_connection()
            row = conn.execute(
                "SELECT COUNT(*), "
                "COALESCE(SUM(CASE WHEN adopted_at >= datetime('now', '-30 days') THEN 1 ELSE 0 END), 0), "
                "COUNT(DISTINCT knowledge_id) "
                "FROM v1_knowledge_adoptions WHERE case_id = ? AND decision = 'adopted'",
                (case_id,),
            ).fetchone()
            return {
                "adoptions_total": row[0] or 0,
                "adoptions_30d": row[1] or 0,
                "distinct_knowledge": row[2] or 0,
            }
        except Exception:
            return {"adoptions_total": 0, "adoptions_30d": 0, "distinct_knowledge": 0}

    def list_adoptions(self, knowledge_id: str) -> list[dict[str, Any]]:
        """C12 R16: 列出该 knowledge 的所有 adoptions (按 adopted_at 倒序).

        condition_diff JSON 反序列化在 service 内完成, api 只包装 version。
        """
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, case_id, knowledge_revision, decision, condition_diff_json, "
            "outcome, outcome_note, adopted_at, adopted_by, decided_by "
            "FROM v1_knowledge_adoptions WHERE knowledge_id = ? "
            "ORDER BY adopted_at DESC",
            (knowledge_id,),
        ).fetchall()
        items: list[dict[str, Any]] = []
        for r in rows:
            try:
                diff = json.loads(r[4]) if r[4] else []
            except (json.JSONDecodeError, TypeError):
                diff = []
            items.append({
                "id": r[0], "case_id": r[1], "knowledge_revision": r[2],
                "decision": r[3], "condition_diff": diff,
                "outcome": r[5], "outcome_note": r[6],
                "adopted_at": r[7], "adopted_by": r[8], "decided_by": r[9],
            })
        return items

    def recall_for_case(
        self, case_id: str, *, knowledge_id: str,
    ) -> dict[str, Any]:
        """C12 R16.3: 召回 — 返回 {applicable, prerequisite_match,
        counter_example_conflict, adoption_history}.

        applicable  = knowledge.status in (published, deprecated) AND case 存在
        prerequisite_match: 本次 case 是否满足知识 prerequisites
        counter_example_conflict: 本次 case 是否撞到 counter_examples
        adoption_history: 同 knowledge + 其他 case 的 adoption 历史
                          [{case_id, condition_diff, outcome, adopted_at}, ...]
        """
        k = self._require(knowledge_id)
        conn = get_connection()
        # 拿 knowledge 静态条件
        prereqs = list(k.get("prerequisites") or [])
        counters = list(k.get("counter_examples") or [])
        # 拿 case 的 (T08 暂未存 prerequisites 字段, 用 tags_json 弱匹配)
        row = conn.execute("SELECT tags_json FROM v1_cases WHERE id = ?", (case_id,)).fetchone()
        case_tags = json.loads(row[0]) if row and row[0] else []
        # 弱匹配: 知识 prereq 在 case tags 出现 → 满足
        prereq_match = all(p in case_tags for p in prereqs) if prereqs else True
        counter_conflict = any(c in case_tags for c in counters) if counters else False
        # 召回其他 case 的 adoption 历史 (排除当前 case 本身)
        history_rows = conn.execute(
            "SELECT case_id, condition_diff_json, outcome, adopted_at, decision "
            "FROM v1_knowledge_adoptions WHERE knowledge_id = ? "
            "AND case_id != ? ORDER BY adopted_at DESC",
            (knowledge_id, case_id),
        ).fetchall()
        adoption_history: list[dict[str, Any]] = []
        for cr, cdf, out, at, dec in history_rows:
            try:
                cdf_parsed = json.loads(cdf) if cdf else []
            except (json.JSONDecodeError, TypeError):
                cdf_parsed = []
            adoption_history.append({
                "case_id": cr, "condition_diff": cdf_parsed,
                "outcome": out, "adopted_at": at, "decision": dec,
            })
        return {
            "knowledge_id": knowledge_id,
            "case_id": case_id,
            "applicable": k["status"] in ("published", "deprecated"),
            "knowledge_status": k["status"],
            "prerequisite_match": prereq_match,
            "counter_example_conflict": counter_conflict,
            "prerequisites": prereqs,
            "counter_examples": counters,
            "adoption_history": adoption_history,
        }

    def _attach_blocker_to_adopted_cases(
        self, knowledge_id: str, marker: str,
    ) -> int:
        """C12 R16.4 辅助: 扫 v1_knowledge_adoptions WHERE decision=adopted,
        给每个 case 挂 marker tag (无重复). 返受影响 case 数.

        append-only: 不写 adoption 历史 (旧行不动).
        """
        conn = get_connection()
        rows = conn.execute(
            "SELECT DISTINCT case_id FROM v1_knowledge_adoptions "
            "WHERE knowledge_id = ? AND decision = 'adopted'",
            (knowledge_id,),
        ).fetchall()
        affected = 0
        for (case_id,) in rows:
            row = conn.execute(
                "SELECT tags_json FROM v1_cases WHERE id = ?", (case_id,),
            ).fetchone()
            if row is None:
                continue
            tags = json.loads(row[0] or "[]")
            if marker in tags:
                continue
            tags.append(marker)
            conn.execute(
                "UPDATE v1_cases SET tags_json = ?, "
                "updated_at = datetime('now', 'localtime') WHERE id = ?",
                (json.dumps(tags, ensure_ascii=False), case_id),
            )
            affected += 1
        if affected:
            conn.commit()
        return affected

    # ------------------------------------------------------------------
    # SK-06 复查扫描 (供 scheduler job 调用)
    # ------------------------------------------------------------------
    def scan_review_due(self, now_iso: str | None = None) -> list[dict[str, Any]]:
        """扫 review_at <= now AND status=published; 返回待复查 knowledge 列表."""
        now = now_iso or _utcnow_iso()
        return self.repo.list_published_due_for_review(now)

    def mark_case_blocker(self, case_id: str, knowledge_id: str) -> bool:
        """SK-06: 挂 blocker 到 case (v1_cases.tags_json 加 'knowledge_review_due:{knowledge_id}')."""
        conn = get_connection()
        row = conn.execute("SELECT tags_json FROM v1_cases WHERE id = ?", (case_id,)).fetchone()
        if row is None:
            return False
        import json
        tags = json.loads(row[0] or "[]")
        marker = f"knowledge_review_due:{knowledge_id}"
        if marker not in tags:
            tags.append(marker)
            conn.execute(
                "UPDATE v1_cases SET tags_json = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
                (json.dumps(tags, ensure_ascii=False), case_id),
            )
            conn.commit()
        return True


# ---------------------------------------------------------------------------
# v0.8.5 D3 (SK-05 升级): Case 创建时自动召回 — 复利飞轮的「传动」
# ---------------------------------------------------------------------------
_CVE_RE = re.compile(r"CVE-\d{4}-\d{4,7}", re.IGNORECASE)
_WORD_RE = re.compile(r"[\w\u4e00-\u9fff]{2,}")


def auto_recall_for_case(case: dict[str, Any], *, limit: int = 3) -> list[dict[str, Any]]:
    """已发布知识 × Case 文本 自动匹配 (读时召回, 无写入).

    匹配语义 (诚实可解释 — 每条候选带 reasons, 不做黑盒打分):
      - CVE 编号命中 (标题/正文) → +5, 单独即可入选
      - 关键词 (case 标题+问题切词, ≥2 字) 命中 → +1/词 (上限 5), 需 ≥2 分入选
    仅 published 参与召回; deprecated/retracted/draft 不出现 (失效知识不作依据).

    Returns
    -------
    [{id, title, kind, revision, score, reasons}] — 按 score DESC, top limit.
    """
    text = f"{case.get('title', '')} {case.get('question', '')}"
    cves = {c.upper() for c in _CVE_RE.findall(text)}
    words = {w.lower() for w in _WORD_RE.findall(text)}
    if not cves and not words:
        return []
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, title, body, kind, revision FROM v1_knowledge WHERE status = 'published'"
        ).fetchall()
    except sqlite3.OperationalError as e:
        logger.warning(f"auto_recall: v1_knowledge unavailable: {e}")
        return []
    scored: list[dict[str, Any]] = []
    for kid, title, body, kind, revision in rows:
        blob = f"{title or ''} {body or ''}".lower()
        score = 0
        reasons: list[str] = []
        for c in cves:
            if c.lower() in blob:
                score += 5
                reasons.append(f"CVE {c} 命中")
        hits = sorted(w for w in words if w in blob)
        if hits:
            score += min(len(hits), 5)
            shown = "、".join(hits[:4]) + ("…" if len(hits) > 4 else "")
            reasons.append(f"关键词 {len(hits)} 命中 ({shown})")
        if score >= (5 if cves else 2):
            scored.append({
                "id": kid, "title": title, "kind": kind,
                "revision": revision, "score": score, "reasons": reasons,
            })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


def add_agent_link(
    from_id: str, to_id: str, link_type: str, confidence: float,
) -> int:
    """MCP tool link_items 写路径 — agent 持久化 item 间关系 (knowledge_links).

    Batch 2 D: 自 mcp_agent_tools 下沉; created_by 固定 'agent',
    返回新行 link_id。连接为 autocommit (isolation_level=None),
    与原 api 直写行为逐字一致。
    """
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO knowledge_links "
        "(from_item_id, to_item_id, link_type, confidence, created_by) "
        "VALUES (?, ?, ?, ?, 'agent')",
        (from_id, to_id, link_type, confidence),
    )
    return cur.lastrowid
