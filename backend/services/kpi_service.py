"""kpi_service.py — P3-C KPI 观测查询 (DEV-0289)。

口径裁决 (DEV-0281/0284 + P2-6 行业对标): signals/hotspots 转化率带与质量
门槛结构性不可兼得 (15-30% 带退场), 主指标切换为:
  1. triage_latency  — signal→case 分诊时延 (P50/P90, 对标 Gemini Triage
     "30min→60s" 量纲)
  2. artifact_yield  — run 产物产出率 (done 且 artifact≥1 / done 总数,
     「禁止成功但无产物」的正面量纲)
  3. signals_ratio   — signals/hotspots 比率 **降级为参考值** (不再设门)

纯只读聚合; SQL 在 service 层 (api 禁直连, R3)。窗口参数化 (默认 30d,
时延需要样本量; 产出率默认 7d 贴 "任一失败 24h 可查" 的运营节奏)。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from backend.repository.db import get_connection

# v1 表的 created_at 格式**混用**: 生产实测 `v1_cases` 6 行里 5 行 ISO
# (`T` 分隔) + 1 行 SQLite 原生 (空格分隔)。只认一种 → 另一种被静默跳过。
_TS_FORMATS = ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S")


def _parse_ts(raw: object) -> datetime | None:
    """解析时间戳 → naive datetime; 两种分隔符都认, 解析不了返回 None。"""
    s = str(raw or "")[:19]
    for fmt in _TS_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


class KpiService:
    """跨 v1 表 KPI 聚合查询 (只读)。"""

    def triage_latency(self, *, days: int = 30) -> dict[str, Any]:
        """signal→case 分诊时延: case.related_signal_ids_json 首信号 → case 创建。

        无关联信号的 case 不计入样本 (时延不可定义, 诚实缺省)。
        """
        rows = get_connection().execute(
            "SELECT c.created_at, c.related_signal_ids_json FROM v1_cases c "
            # datetime() 包一层: 裸字符串比较在格式混用时不可靠 (边界日
            # `'...T08:00' >= '... 07:00'` 恒真 → 窗外的行被误纳)
            "WHERE datetime(c.created_at) >= datetime('now', ?) "
            "ORDER BY datetime(c.created_at)",
            (f"-{int(days)} days",),
        ).fetchall()
        latencies: list[float] = []
        cases_total = len(rows)
        for created_at, sig_json in rows:
            try:
                sig_ids = json.loads(sig_json or "[]")
            except (TypeError, ValueError):
                continue
            if not sig_ids:
                continue
            sig = get_connection().execute(
                "SELECT created_at FROM v1_signals WHERE id = ?", (sig_ids[0],)
            ).fetchone()
            if not sig or not sig[0]:
                continue
            t0 = _parse_ts(sig[0])
            t1 = _parse_ts(created_at)
            if t0 is None or t1 is None:
                continue
            latencies.append((t1 - t0).total_seconds())
        latencies.sort()
        n = len(latencies)

        def _pct(p: float) -> float | None:
            if not n:
                return None
            idx = min(n - 1, round(p * (n - 1)))
            return round(latencies[idx], 1)

        return {
            "window_days": int(days),
            "cases_total": cases_total,
            "samples": n,
            "p50_seconds": _pct(0.5),
            "p90_seconds": _pct(0.9),
            "min_seconds": latencies[0] if n else None,
            "max_seconds": latencies[-1] if n else None,
        }

    def artifact_yield(self, *, days: int = 7) -> dict[str, Any]:
        """run 产物产出率: done 且 artifact_ids_json 非空 / done 总数。

        「禁止成功但无产物」(run ledger 核心纪律) 的正面量纲 — 目标 = 1.0。
        v0.8.9 D7 口径修复: 分母改 `outcome = 'done'` — 原实现写 `status = 'done'`,
        而 7 态机终态是 `status='succeeded' + outcome='done'`, 全仓无代码写
        status='done' → 分母恒 0 恒 None (勘察断点⑥)。
        """
        total, with_art = get_connection().execute(
            "SELECT COUNT(*), "
            "SUM(artifact_ids_json IS NOT NULL AND artifact_ids_json != '[]') "
            "FROM v1_runs WHERE outcome = 'done' "
            "AND created_at >= datetime('now', ?)",
            (f"-{int(days)} days",),
        ).fetchone()
        total = int(total or 0)
        with_art = int(with_art or 0)
        return {
            "window_days": int(days),
            "runs_done": total,
            "runs_with_artifact": with_art,
            "yield_ratio": round(with_art / total, 4) if total else None,
        }

    def signals_ratio(self, *, days: int = 7) -> dict[str, Any]:
        """signals/hotspots 比率 — **降级参考值** (P3-C 口径裁决, 不再设带)。"""
        s, h = get_connection().execute(
            "SELECT (SELECT COUNT(*) FROM v1_signals WHERE created_at >= datetime('now', ?)), "
            "(SELECT COUNT(*) FROM hotspots WHERE ingested_at >= datetime('now', ?))",
            (f"-{int(days)} days", f"-{int(days)} days"),
        ).fetchone()
        s, h = int(s or 0), int(h or 0)
        return {
            "window_days": int(days),
            "signals": s,
            "hotspots": h,
            "ratio": round(s / h, 4) if h else None,
            "note": "降级参考值 (P3-C): 带与质量门槛结构性不可兼得, 不再作为门",
        }


__all__ = ["KpiService"]
