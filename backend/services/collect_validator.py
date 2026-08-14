"""v1.9 Phase 9 — 数据完整性验证 (4 类).

设计
----
一个 run 完成后调 :func:`validate_run(run_id)` 返回 :class:`ValidationReport`,
内部依次跑 4 类检查, 每类检查可能产出 0..N 条 :class:`ValidationIssue`:

1. **source_regression** (源退化)
   - 比较: 该 (category, source_name) 在历史 7 天平均 yield vs 本次 yield
   - 历史 yield > 0 但本次 = 0 → severity=warn
   - 历史 yield > 0 但本次 < 历史 30% → severity=info

2. **time_coverage_gap** (时间窗口覆盖缺口)
   - 把 [since, until] 切成 1h bins, 统计每个 bin 内的 ingested_at 数量
   - 连续 ≥3 个空 bin → severity=warn
   - 单独 1 个空 bin → severity=info (避免误报, 单小时没新闻是常态)

3. **category_anomaly** (分类级总量异常)
   - 比较: 本次 category items_count vs 过去 7 天同 category 的 avg
   - 本次 > 2x avg → severity=info (可能重复抓, 但不一定)
   - 本次 < 0.3x avg AND 历史 avg > 5 → severity=warn (源大面积失效)
   - 本次 = 0 AND 历史 avg > 0 → severity=error (整分类断了)

4. **cross_source** (跨源一致性)
   - 简单实现: 把 [since, until] 内所有 items 的 title 标准化
     (lowercase + 去标点 + 拆词, 取前 3 个非停用词)
   - 按 (category, title_key) 分组, 统计 distinct source_name 数
   - 总簇数: total_clusters
   - 多源覆盖簇数: clusters_with_sources >= 2
   - ratio = multi / total
   - ratio > 0.8 → severity=info (同事件被多源大量转载, 可能 scrape 重复)
   - ratio < 0.2 AND total >= 10 → severity=info (源之间太孤立)

非阻塞
----
所有检查 :func:`log_collection_validation` 写 :class:`collect_validations` 表,
不抛异常, 不影响 catchup 终态.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from backend.repository.db import get_connection


class ValidationType(str, Enum):
    SOURCE_REGRESSION = "source_regression"
    TIME_COVERAGE_GAP = "time_coverage_gap"
    CATEGORY_ANOMALY = "category_anomaly"
    CROSS_SOURCE = "cross_source"


class Severity(str, Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


@dataclass
class ValidationIssue:
    validation_type: str
    severity: str
    payload: dict[str, Any]

    def to_dict(self) -> dict:
        return {
            "validation_type": self.validation_type,
            "severity": self.severity,
            "payload": self.payload,
        }


@dataclass
class ValidationReport:
    run_id: int
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == "warn" for i in self.issues)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "issues": [i.to_dict() for i in self.issues],
            "total": len(self.issues),
            "errors": sum(1 for i in self.issues if i.severity == "error"),
            "warnings": sum(1 for i in self.issues if i.severity == "warn"),
        }


# ---------------------------------------------------------------------------
# 持久化 helper
# ---------------------------------------------------------------------------
def _persist_issue(run_id: int, issue: ValidationIssue) -> None:
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO collect_validations
            (run_id, validation_type, severity, payload, detected_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            int(run_id),
            issue.validation_type,
            issue.severity,
            json.dumps(issue.payload, ensure_ascii=False)[:2000],
            datetime.now(timezone.utc).isoformat(),
        ),
    )


def persist_report(report: ValidationReport) -> None:
    """把整个 report 写库 (供后续 /api/health 查询)."""
    for issue in report.issues:
        _persist_issue(report.run_id, issue)


# ---------------------------------------------------------------------------
# 4 类检查
# ---------------------------------------------------------------------------
def _check_source_regression(
    run_id: int, since_iso: str, until_iso: str
) -> list[ValidationIssue]:
    """源退化: 历史 yield > 0 但本次 yield = 0 (或 < 30%)."""
    try:
        conn = get_connection()
        # 本次: 从 catchup_checkpoints 读 (最准确)
        current = conn.execute(
            """
            SELECT category, source_name, items_count FROM catchup_checkpoints
            WHERE run_id = ? AND status = 'done'
            """,
            (int(run_id),),
        ).fetchall()
        current_map: dict[tuple[str, str], int] = {
            (str(r["category"]), str(r["source_name"])): int(r["items_count"])
            for r in current
        }
        # 历史: 过去 7 天同 (cat, src) 的 avg items_count
        # 数据源: catchup_checkpoints 中 finished_at >= now-7d 的 done 行
        seven_days_ago = (
            datetime.now(timezone.utc) - timedelta(days=7)
        ).isoformat()
        history_rows = conn.execute(
            """
            SELECT category, source_name, AVG(items_count) AS avg_count,
                   COUNT(*) AS runs
            FROM catchup_checkpoints
            WHERE status = 'done' AND finished_at >= ? AND run_id != ?
            GROUP BY category, source_name
            """,
            (seven_days_ago, int(run_id)),
        ).fetchall()
        history_map: dict[tuple[str, str], float] = {
            (str(r["category"]), str(r["source_name"])): float(r["avg_count"])
            for r in history_rows
            if float(r["avg_count"] or 0) > 0
        }
        issues: list[ValidationIssue] = []
        for key, hist_avg in history_map.items():
            cur = current_map.get(key, 0)
            if cur == 0 and hist_avg > 0:
                issues.append(ValidationIssue(
                    validation_type=ValidationType.SOURCE_REGRESSION.value,
                    severity=Severity.WARN.value,
                    payload={
                        "category": key[0],
                        "source_name": key[1],
                        "history_avg": round(hist_avg, 1),
                        "current": 0,
                        "regression_pct": 100.0,
                    },
                ))
            elif cur > 0 and hist_avg > 0 and cur < 0.3 * hist_avg:
                issues.append(ValidationIssue(
                    validation_type=ValidationType.SOURCE_REGRESSION.value,
                    severity=Severity.INFO.value,
                    payload={
                        "category": key[0],
                        "source_name": key[1],
                        "history_avg": round(hist_avg, 1),
                        "current": cur,
                        "regression_pct": round((1 - cur / hist_avg) * 100, 1),
                    },
                ))
        return issues
    except Exception as e:
        return [ValidationIssue(
            validation_type=ValidationType.SOURCE_REGRESSION.value,
            severity=Severity.WARN.value,
            payload={"error": f"check crashed: {type(e).__name__}: {str(e)[:200]}"},
        )]


def _check_time_coverage_gap(
    run_id: int, since_iso: str, until_iso: str
) -> list[ValidationIssue]:
    """时间窗口覆盖缺口: 1h bins, 连续 ≥3 个空 bin → warn."""
    try:
        since = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
        until = datetime.fromisoformat(until_iso.replace("Z", "+00:00"))
        if until <= since:
            return []
        # 1h bins
        bins: list[tuple[datetime, datetime]] = []
        cur = since
        while cur < until:
            nxt = cur + timedelta(hours=1)
            bins.append((cur, min(nxt, until)))
            cur = nxt
        if not bins:
            return []
        # 查询 [since, until] 内 items 的 ingested_at 分布
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT ingested_at FROM hotspots
            WHERE ingested_at >= ? AND ingested_at < ?
            """,
            (since_iso, until_iso),
        ).fetchall()
        ts_list: list[datetime] = []
        for r in rows:
            try:
                ts_list.append(datetime.fromisoformat(str(r["ingested_at"]).replace("Z", "+00:00")))
            except Exception:
                pass
        # 计数
        bin_counts = [0] * len(bins)
        for ts in ts_list:
            for i, (b_start, b_end) in enumerate(bins):
                if b_start <= ts < b_end:
                    bin_counts[i] += 1
                    break
        issues: list[ValidationIssue] = []
        # 找连续空段
        empty_streak = 0
        empty_streak_start = -1
        for i, c in enumerate(bin_counts):
            if c == 0:
                if empty_streak == 0:
                    empty_streak_start = i
                empty_streak += 1
            else:
                if empty_streak >= 3:
                    issues.append(ValidationIssue(
                        validation_type=ValidationType.TIME_COVERAGE_GAP.value,
                        severity=Severity.WARN.value,
                        payload={
                            "gap_start": bins[empty_streak_start][0].isoformat(),
                            "gap_end": bins[i - 1][1].isoformat(),
                            "empty_hours": empty_streak,
                        },
                    ))
                empty_streak = 0
                empty_streak_start = -1
        # 尾部
        if empty_streak >= 3:
            issues.append(ValidationIssue(
                validation_type=ValidationType.TIME_COVERAGE_GAP.value,
                severity=Severity.WARN.value,
                payload={
                    "gap_start": bins[empty_streak_start][0].isoformat(),
                    "gap_end": bins[-1][1].isoformat(),
                    "empty_hours": empty_streak,
                },
            ))
        return issues
    except Exception as e:
        return [ValidationIssue(
            validation_type=ValidationType.TIME_COVERAGE_GAP.value,
            severity=Severity.WARN.value,
            payload={"error": f"check crashed: {type(e).__name__}: {str(e)[:200]}"},
        )]


def _check_category_anomaly(
    run_id: int, since_iso: str, until_iso: str
) -> list[ValidationIssue]:
    """分类级总量异常: vs 过去 7 天同 category avg."""
    try:
        conn = get_connection()
        # 本次: 该 run 的 catchup_checkpoints 聚合
        current = conn.execute(
            """
            SELECT category, SUM(items_count) AS total FROM catchup_checkpoints
            WHERE run_id = ? AND status IN ('done', 'skipped')
            GROUP BY category
            """,
            (int(run_id),),
        ).fetchall()
        current_map: dict[str, int] = {
            str(r["category"]): int(r["total"] or 0) for r in current
        }
        # 历史: 过去 7 天按 category 聚合
        seven_days_ago = (
            datetime.now(timezone.utc) - timedelta(days=7)
        ).isoformat()
        history_rows = conn.execute(
            """
            SELECT category, AVG(total) AS avg_count FROM (
                SELECT category, run_id, SUM(items_count) AS total
                FROM catchup_checkpoints
                WHERE status = 'done' AND finished_at >= ? AND run_id != ?
                GROUP BY run_id, category
            ) GROUP BY category
            """,
            (seven_days_ago, int(run_id)),
        ).fetchall()
        history_map: dict[str, float] = {
            str(r["category"]): float(r["avg_count"] or 0) for r in history_rows
        }
        issues: list[ValidationIssue] = []
        for cat, hist_avg in history_map.items():
            if hist_avg < 1:
                continue  # 样本太少, 跳过
            cur = current_map.get(cat, 0)
            if cur == 0:
                issues.append(ValidationIssue(
                    validation_type=ValidationType.CATEGORY_ANOMALY.value,
                    severity=Severity.ERROR.value,
                    payload={
                        "category": cat,
                        "history_avg": round(hist_avg, 1),
                        "current": 0,
                        "type": "total_zero",
                    },
                ))
            elif cur < 0.3 * hist_avg:
                issues.append(ValidationIssue(
                    validation_type=ValidationType.CATEGORY_ANOMALY.value,
                    severity=Severity.WARN.value,
                    payload={
                        "category": cat,
                        "history_avg": round(hist_avg, 1),
                        "current": cur,
                        "type": "below_30pct",
                    },
                ))
            elif cur > 2.0 * hist_avg:
                issues.append(ValidationIssue(
                    validation_type=ValidationType.CATEGORY_ANOMALY.value,
                    severity=Severity.INFO.value,
                    payload={
                        "category": cat,
                        "history_avg": round(hist_avg, 1),
                        "current": cur,
                        "type": "above_2x",
                    },
                ))
        return issues
    except Exception as e:
        return [ValidationIssue(
            validation_type=ValidationType.CATEGORY_ANOMALY.value,
            severity=Severity.WARN.value,
            payload={"error": f"check crashed: {type(e).__name__}: {str(e)[:200]}"},
        )]


# 简单 title 标准化: lowercase + 去标点 + 拆词 + 取前 3 个非停用词
_STOPWORDS = {"the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are", "at", "with", "by"}
_TITLE_NORMALIZE = re.compile(r"[^a-z0-9\s\u4e00-\u9fff]")


def _title_key(title: str) -> str:
    s = title.lower()
    s = _TITLE_NORMALIZE.sub(" ", s)
    tokens = [t for t in s.split() if t and t not in _STOPWORDS]
    # 中文不分词, 直接用全 title 的小写形式
    if not tokens:
        return s.strip()[:50]
    return " ".join(tokens[:3])


def _check_cross_source(
    run_id: int, since_iso: str, until_iso: str
) -> list[ValidationIssue]:
    """跨源一致性: 同一 (category, title_key) 是否有多源覆盖."""
    try:
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT category, source AS source_name, title FROM hotspots
            WHERE ingested_at >= ? AND ingested_at < ?
              AND title IS NOT NULL AND title != ''
            """,
            (since_iso, until_iso),
        ).fetchall()
        # 聚合: (category, title_key) -> set(source_name)
        clusters: dict[tuple[str, str], set[str]] = defaultdict(set)
        for r in rows:
            cat = str(r["category"])
            src = str(r["source_name"])
            key = _title_key(str(r["title"]))
            if key:
                clusters[(cat, key)].add(src)
        if not clusters:
            return []
        total = len(clusters)
        multi = sum(1 for v in clusters.values() if len(v) >= 2)
        ratio = multi / total if total else 0
        issues: list[ValidationIssue] = []
        if total >= 10 and ratio < 0.2:
            issues.append(ValidationIssue(
                validation_type=ValidationType.CROSS_SOURCE.value,
                severity=Severity.INFO.value,
                payload={
                    "type": "low_overlap",
                    "total_clusters": total,
                    "multi_source_clusters": multi,
                    "ratio": round(ratio, 3),
                    "hint": "源之间太孤立, 可能 scrape 受限或标题不规范化",
                },
            ))
        elif ratio > 0.8:
            issues.append(ValidationIssue(
                validation_type=ValidationType.CROSS_SOURCE.value,
                severity=Severity.INFO.value,
                payload={
                    "type": "high_overlap",
                    "total_clusters": total,
                    "multi_source_clusters": multi,
                    "ratio": round(ratio, 3),
                    "hint": "同事件多源大量转载, 可能 scrape 重复",
                },
            ))
        return issues
    except Exception as e:
        return [ValidationIssue(
            validation_type=ValidationType.CROSS_SOURCE.value,
            severity=Severity.WARN.value,
            payload={"error": f"check crashed: {type(e).__name__}: {str(e)[:200]}"},
        )]


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def validate_run(run_id: int, since_iso: str, until_iso: str) -> ValidationReport:
    """跑全部 4 类检查, 返回报告 (不抛异常).

    Parameters
    ----------
    run_id : int
        catchup_runs.id
    since_iso, until_iso : str
        抓取时间窗口 (ISO 8601 UTC)

    Returns
    -------
    ValidationReport
        含 0..N 个 issue. 失败时单个 issue 描述错误, 不阻塞主流程.
    """
    report = ValidationReport(run_id=run_id)
    report.issues.extend(_check_source_regression(run_id, since_iso, until_iso))
    report.issues.extend(_check_time_coverage_gap(run_id, since_iso, until_iso))
    report.issues.extend(_check_category_anomaly(run_id, since_iso, until_iso))
    report.issues.extend(_check_cross_source(run_id, since_iso, until_iso))
    return report


def auto_resolve_old_validations(*, older_than_days: int = 7) -> int:
    """P1-1: 自动归档旧的 unresolved validation issues.

    7d 前 (detected_at < now - 7d) 且未 resolved 的 issues
    标 resolved_at=now, 避免表无限累积 + 污染前端展示.

    保留策略
    --------
    - 7d 前 unresolved → resolved (软删除, 保留历史)
    - 不物理删除 — 30d 后可由专门清理 job 物理删 (本期不做)
    - 删除条件: resolved_at IS NULL AND detected_at < cutoff

    Returns
    -------
    int
        被归档的 issue 数
    """
    from datetime import datetime, timedelta, timezone

    from backend.repository.db import get_connection
    try:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=older_than_days)
        ).isoformat()
        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        cur = conn.execute(
            """
            UPDATE collect_validations
            SET resolved_at = ?
            WHERE resolved_at IS NULL
              AND detected_at < ?
            """,
            (now, cutoff),
        )
        return int(cur.rowcount or 0)
    except Exception as e:
        # 单条失败不抛, 让 job 续跑
        import logging
        logging.getLogger(__name__).warning(
            f"auto_resolve_old_validations failed: {e}"
        )
        return 0


def list_recent_validations(
    run_id: int | None = None,
    *,
    include_resolved: bool = False,
    limit: int = 50,
) -> list[ValidationIssue]:
    """P1-3: 列出最近的 validation issues (供 /api/catchup/status).

    Parameters
    ----------
    run_id : int, optional
        指定 run_id; None = 跨 run 取最近 N 条
    include_resolved : bool
        是否包含已 resolved 的 (默认 False)
    limit : int
        最多返回 N 条
    """
    from backend.repository.db import get_connection
    try:
        conn = get_connection()
        if run_id is not None:
            sql = """
                SELECT * FROM collect_validations
                WHERE run_id = ?
            """
            params: list = [int(run_id)]
            if not include_resolved:
                sql += " AND resolved_at IS NULL"
            sql += " ORDER BY detected_at DESC LIMIT ?"
            params.append(int(limit))
            rows = conn.execute(sql, tuple(params)).fetchall()
        else:
            sql = """
                SELECT * FROM collect_validations
                WHERE 1=1
            """
            params = []
            if not include_resolved:
                sql += " AND resolved_at IS NULL"
            sql += " ORDER BY detected_at DESC LIMIT ?"
            params.append(int(limit))
            rows = conn.execute(sql, tuple(params)).fetchall()
        out: list[ValidationIssue] = []
        for r in rows:
            try:
                payload = json.loads(r["payload"]) if r["payload"] else {}
            except Exception:
                payload = {"raw": r["payload"]}
            out.append(ValidationIssue(
                validation_type=str(r["validation_type"]),
                severity=str(r["severity"]),
                payload=payload,
            ))
        return out
    except Exception:
        return []


def validate_and_persist(
    run_id: int, since_iso: str, until_iso: str
) -> ValidationReport:
    """跑 + 持久化 + 写日志 (一站式)."""
    report = validate_run(run_id, since_iso, until_iso)
    persist_report(report)
    # 写日志
    try:
        from backend.services.collection_logger import log_collect_event
        log_collect_event(
            "validate_done",
            run_id=int(run_id),
            total=len(report.issues),
            errors=sum(1 for i in report.issues if i.severity == "error"),
            warnings=sum(1 for i in report.issues if i.severity == "warn"),
            infos=sum(1 for i in report.issues if i.severity == "info"),
        )
    except Exception:
        pass
    return report


__all__ = [
    "Severity",
    "ValidationIssue",
    "ValidationReport",
    "ValidationType",
    "persist_report",
    "validate_and_persist",
    "validate_run",
]
