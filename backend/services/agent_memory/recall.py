"""v0.8 B3 — 记忆召回: 三路混合检索 (关键词 LIKE / simhash / skill_id 精确).

数据源 = ``skill_runs`` 表 (intent 从 inputs JSON 提取, 兜底用 result 摘要),
不建额外索引表 — 单用户量级下直接扫最近若干条可接受 (约束见 B3 任务书)。

三路策略 (合并去重优先级: 精确 > simhash > 关键词):
1. **keyword (廉价初筛)** — 取 intent 的 2-3 个关键词对
   ``skill_runs.result`` / ``inputs`` 做多 pattern OR LIKE。
   SQLite 无 trigram 索引, 这是保守的子串初筛替代。
2. **simhash (语义指纹)** — 纯 python 64-bit simhash 对比 intent 与
   历史 run 的 intent 文本, 海明距离 ≤12 视为相似。
3. **exact (tag/结构化)** — 历史 skill_id 在 intent 中出现即精确命中。
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from typing import Any

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.db import get_connection
from backend.services.agent_memory.memory import MemoryHit

# 海明距离阈值: ≤12 / 64 bit 视为相似 (经验值, 覆盖少量 token 增删)
SIMHASH_MAX_DISTANCE = 12

# simhash 扫描窗口: 只对比最近 N 条 run (单用户量级, 不建索引表的代价上限)
_RECALL_SCAN_LIMIT = 200

_CJK_CHAR = re.compile(r"[\u4e00-\u9fff]")
_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")

# match_path → 合并优先级 (越小越优先)
_PATH_PRIORITY = {"exact": 0, "simhash": 1, "keyword": 2}


# ---------------------------------------------------------------------------
# 文本工具 (包内共享: miner.py 复用 tokenize / top_keywords)
# ---------------------------------------------------------------------------
def tokenize(text: str) -> list[str]:
    """切词: ASCII 按词 (lower), 中文按单字 + 相邻 bigram.

    中文无空格分词, 单字 + bigram 是 simhash 与关键词抽取的最小可靠单元;
    bigram 显著提升短中文 intent 的指纹区分度。
    """
    if not text:
        return []
    out: list[str] = []
    for m in _TOKEN_RE.finditer(text):
        tok = m.group(0)
        out.append(tok.lower() if not _CJK_CHAR.match(tok[0]) else tok)
    chars = [c for c in text if _CJK_CHAR.match(c)]
    out.extend(a + b for a, b in zip(chars, chars[1:]))
    return out


def top_keywords(texts: list[str], limit: int = 3) -> list[str]:
    """从一批文本里取频率最高的 top-N 关键词 (词长 ≥2, 频率同则长词优先).

    供 recall 关键词初筛与 miner 的 prefer_style value 摘要复用。
    """
    freq: dict[str, int] = {}
    for text in texts:
        for tok in tokenize(text):
            if len(tok) >= 2:
                freq[tok] = freq.get(tok, 0) + 1
    ranked = sorted(freq.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))
    return [tok for tok, _ in ranked[:limit]]


def simhash64(text: str) -> int:
    """纯 python 64-bit simhash 指纹 (md5 token 哈希逐位加权投票)."""
    bits = [0] * 64
    for tok in tokenize(text):
        digest = hashlib.md5(tok.encode("utf-8")).digest()
        v = int.from_bytes(digest[:8], "big")
        for i in range(64):
            bits[i] += 1 if (v >> i) & 1 else -1
    fingerprint = 0
    for i, weight in enumerate(bits):
        if weight > 0:
            fingerprint |= 1 << i
    return fingerprint


def hamming_distance(a: int, b: int) -> int:
    """两个 64-bit 指纹的海明距离."""
    return bin(a ^ b).count("1")


def extract_intent(inputs_json: str | None) -> str:
    """从 skill_runs.inputs (JSON) 提取 intent 文本.

    依次尝试 intent / query / prompt / text / task 键; 均缺失时拼接
    全部标量值兜底; inputs 非 JSON 时原样返回 (尽力而为, 不抛错)。
    """
    if not inputs_json:
        return ""
    try:
        data = json.loads(inputs_json)
    except (TypeError, ValueError):
        return inputs_json
    if not isinstance(data, dict):
        return str(data)
    for key in ("intent", "query", "prompt", "text", "task"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return " ".join(
        str(v) for v in data.values() if isinstance(v, (str, int, float))
    )


# ---------------------------------------------------------------------------
# 召回引擎
# ---------------------------------------------------------------------------
class MemoryRecall:
    """基于 skill_runs 历史的三路混合召回."""

    def search(self, intent: str, k: int = 5) -> list[MemoryHit]:
        """按 intent 召回相关历史 run, 三路合并去重后截取前 k 条.

        Parameters
        ----------
        intent : str
            当前用户意图文本。
        k : int
            返回条数上限。

        Returns
        -------
        list[MemoryHit]
            按 (匹配路径优先级, 相似度降序) 排序, 反馈均分已 join。
        """
        # run_id → (路径优先级, 相似度, match_path, 行数据)
        candidates: dict[str, tuple[int, float, str, dict[str, Any]]] = {}

        # 路径 ③: skill_id 精确匹配 (intent 中出现历史 skill_id)
        query_fp = simhash64(intent)
        keywords = top_keywords([intent], limit=3)
        try:
            for skill_id in self._distinct_skill_ids():
                if len(skill_id) >= 3 and skill_id in intent:
                    for row in self._runs_by_skill(skill_id):
                        self._add(candidates, row, "exact", 1.0)
            # 路径 ②: simhash — 最近 N 条 run 逐一比指纹
            if intent.strip():
                for row in self._recent_runs(_RECALL_SCAN_LIMIT):
                    run_intent = row["intent_text"]
                    if not run_intent:
                        continue
                    dist = hamming_distance(query_fp, row["simhash"])
                    if dist <= SIMHASH_MAX_DISTANCE:
                        self._add(
                            candidates, row, "simhash", 1.0 - dist / 64.0
                        )
            # 路径 ①: 关键词 LIKE 廉价初筛 (仅在前两路不足 k 时补齐)
            if len(candidates) < k and keywords:
                for row in self._keyword_runs(keywords):
                    similarity = row["matched_keywords"] / len(keywords)
                    self._add(candidates, row, "keyword", similarity)
        except sqlite3.Error as e:
            logger.error(
                "agent_memory recall failed",
                extra={"trace_id": "", "error": str(e)},
            )
            raise InternalException(f"agent_memory recall failed: {e}") from e

        ranked = sorted(
            candidates.values(),
            key=lambda c: (c[0], -c[1]),
        )[:k]
        hits = [self._to_hit(row, path, sim) for _, sim, path, row in ranked]
        self._attach_feedback_scores(hits)
        return hits

    # ------------------------------------------------------------------
    # 内部: 候选收集
    # ------------------------------------------------------------------
    @staticmethod
    def _add(
        candidates: dict[str, tuple[int, float, str, dict[str, Any]]],
        row: dict[str, Any],
        path: str,
        similarity: float,
    ) -> None:
        """按 run_id 去重合并候选; 高优先级路径 / 高相似度覆盖低值."""
        new_prio = _PATH_PRIORITY.get(path, 9)
        existing = candidates.get(row["run_id"])
        if existing is None:
            candidates[row["run_id"]] = (new_prio, similarity, path, row)
            return
        old_prio, old_sim, old_path, old_row = existing
        if new_prio < old_prio or (new_prio == old_prio and similarity > old_sim):
            candidates[row["run_id"]] = (new_prio, similarity, path, old_row)

    def _distinct_skill_ids(self) -> list[str]:
        """skill_runs 里出现过的全部 skill_id (exact 路径的 tag 字典)."""
        rows = get_connection().execute(
            "SELECT DISTINCT skill_id FROM skill_runs"
        ).fetchall()
        return [r["skill_id"] for r in rows]

    def _runs_by_skill(self, skill_id: str) -> list[dict[str, Any]]:
        """按 skill_id 精确拉取该 skill 的历史 run 行."""
        rows = get_connection().execute(
            "SELECT run_id, skill_id, inputs, result, created_at "
            "FROM skill_runs WHERE skill_id = ? ORDER BY created_at DESC",
            (skill_id,),
        ).fetchall()
        return [self._decorate(r) for r in rows]

    def _recent_runs(self, limit: int) -> list[dict[str, Any]]:
        """最近 N 条 run, 附带 intent 文本与 simhash 指纹."""
        rows = get_connection().execute(
            "SELECT run_id, skill_id, inputs, result, created_at "
            "FROM skill_runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._decorate(r) for r in rows]

    def _keyword_runs(self, keywords: list[str]) -> list[dict[str, Any]]:
        """关键词多 pattern OR LIKE 初筛 (result / inputs 双列)."""
        conds: list[str] = []
        params: list[str] = []
        for kw in keywords:
            conds.append("(result LIKE ? OR inputs LIKE ?)")
            params.extend([f"%{kw}%", f"%{kw}%"])
        rows = get_connection().execute(
            "SELECT run_id, skill_id, inputs, result, created_at "
            f"FROM skill_runs WHERE {' OR '.join(conds)} "
            "ORDER BY created_at DESC LIMIT ?",
            (*params, _RECALL_SCAN_LIMIT),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            decorated = self._decorate(r)
            blob = f"{decorated['result'] or ''} {decorated['intent_text'] or ''}"
            decorated["matched_keywords"] = sum(
                1 for kw in keywords if kw in blob
            )
            out.append(decorated)
        return out

    @staticmethod
    def _decorate(row: sqlite3.Row) -> dict[str, Any]:
        """把 SQL 行加工成候选 dict (附 intent_text / simhash / 摘要)."""
        d = dict(row)
        d["intent_text"] = extract_intent(d.get("inputs"))
        d["simhash"] = simhash64(d["intent_text"])
        return d

    @staticmethod
    def _to_hit(row: dict[str, Any], path: str, similarity: float) -> MemoryHit:
        """候选 dict → MemoryHit (intent 摘要优先, 兜底 result 前缀)."""
        excerpt = row.get("intent_text") or ""
        if not excerpt:
            excerpt = (row.get("result") or "")[:120]
        return MemoryHit(
            skill_run_id=row["run_id"],
            skill_id=row["skill_id"],
            intent_excerpt=excerpt[:120],
            score=0.0,
            created_at=row["created_at"] or "",
            similarity=round(similarity, 4),
            match_path=path,
        )

    @staticmethod
    def _attach_feedback_scores(hits: list[MemoryHit]) -> None:
        """把 feedback_log 按 run 维度的均分 join 进 hit.score (无反馈保持 0)."""
        if not hits:
            return
        placeholders = ",".join("?" for _ in hits)
        rows = get_connection().execute(
            "SELECT skill_run_id, AVG(score) AS avg_score FROM feedback_log "
            f"WHERE skill_run_id IN ({placeholders}) GROUP BY skill_run_id",
            tuple(h.skill_run_id for h in hits),
        ).fetchall()
        scores = {r["skill_run_id"]: r["avg_score"] for r in rows}
        for hit in hits:
            if hit.skill_run_id in scores:
                hit.score = round(float(scores[hit.skill_run_id]), 2)


__all__ = [
    "MemoryRecall",
    "SIMHASH_MAX_DISTANCE",
    "extract_intent",
    "hamming_distance",
    "simhash64",
    "tokenize",
    "top_keywords",
]
