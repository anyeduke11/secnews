"""S4-3 CVE 热力图服务 — 按周 + 严重程度聚合 CVE 数量。

依赖
----
- `attack_loader.load_attack_data()` 启动时已灌入 ATT&CK 数据 (无需本服务调用)
- `security_entities` 表 (entity_type='cve', metadata 可含 cvss)

返回格式
--------
weekly_heatmap(weeks=N) -> {
    "weeks": ["2026-07-26", ...],
    "severities": ["critical", "high", "medium", "low", "none"],
    "matrix": [[w0_critical, w0_high, ...], ...],  # N x 5
}
"""
from __future__ import annotations

import datetime
import json
from typing import Any

from backend.repository.db import get_connection


def _cvss_to_severity(cvss: float | None) -> str:
    """CVSS v3 分值 → severity bucket。"""
    if cvss is None:
        return "none"
    if cvss >= 9.0:
        return "critical"
    if cvss >= 7.0:
        return "high"
    if cvss >= 4.0:
        return "medium"
    return "low"


def weekly_heatmap(weeks: int = 12) -> dict[str, Any]:
    """返回最近 N 周的 CVE 热力图 (按严重程度 5 级)。

    Args:
        weeks: 回溯周数, 默认 12。

    Returns:
        {
            "weeks": [ISO 周字符串],
            "severities": ["critical","high","medium","low","none"],
            "matrix": [[count_critical, count_high, ...], ...]  # len(weeks) x 5
        }
    """
    conn = get_connection()
    cutoff = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(weeks=weeks)
    ).isoformat()

    rows = conn.execute(
        """
        SELECT created_at, metadata
        FROM security_entities
        WHERE entity_type = 'cve'
          AND created_at >= ?
        ORDER BY created_at ASC
        """,
        (cutoff,),
    ).fetchall()

    # 聚合: week_str -> severity -> count
    buckets: dict[str, dict[str, int]] = {}
    for row in rows:
        created = row["created_at"]
        if not created:
            continue
        try:
            dt = datetime.datetime.fromisoformat(created)
            week_str = dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue

        metadata_raw = row["metadata"]
        cvss = None
        if metadata_raw:
            try:
                meta = (
                    json.loads(metadata_raw)
                    if isinstance(metadata_raw, str)
                    else metadata_raw
                )
                cvss = meta.get("cvss")
            except (TypeError, ValueError):
                pass

        severity = _cvss_to_severity(cvss)
        buckets.setdefault(week_str, dict.fromkeys(("critical", "high", "medium", "low", "none"), 0))
        buckets[week_str][severity] += 1

    # 排序并截断到 weeks 个
    week_keys = sorted(buckets.keys())[-weeks:]
    severities = ["critical", "high", "medium", "low", "none"]
    matrix = [[buckets[w][s] for s in severities] for w in week_keys]

    return {
        "weeks": week_keys,
        "severities": severities,
        "matrix": matrix,
    }


__all__ = ["weekly_heatmap"]
