"""v1.8 Phase 8 — 死源复活服务 (Source Revival).

设计要点
--------
- 死源 (``status='dead'``) 在以下情况下可以尝试复活:
  - 已经死够久 (默认 7d, 可调)
  - 源 URL 仍然可达 (HEAD 200/3xx)
- 复活后状态: ``status='active'``, ``zero_yield_runs=0``
- 复活结果会写日志, 但不主动触发全量 collect (让下一个 collect_all 自然带它跑)

为什么需要复活
--------------
source_stats 把 zero_yield_runs 累加到 6 (死阈值) 后会标 dead. 但
dead 是相对当前 collector 配置/网络/反爬策略的快照判断; 几周后源
可能:

- 反爬策略改 (网站被收购/换 CDN)
- 我方网络变化 (代理配置好了, 之前访问不了的现在能)
- 临时下线恢复

所以每日 03:00 跑一次 revive, 给死源一次重生的机会, 避免人工重启
整个 collect pipeline 才能恢复.

实现约束
--------
- HEAD 请求, 5s 超时, 不下载 body (避免流量)
- 用 ``urllib.request`` 而非 aiohttp, 避免额外 event loop 占用
- 单源失败不影响其他源
- 整轮失败不抛, 仅 log (job 主流程)
"""
from __future__ import annotations

import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from backend.logging_config import logger as _root_logger

logger = _root_logger.bind(component="source_revival_service")


# 默认阈值 (可被 settings 覆盖)
DEFAULT_DEAD_FOR_DAYS = 7
DEFAULT_TIMEOUT_S = 5.0


@dataclass
class RevivalResult:
    """单条源的复活结果."""

    category: str
    source_name: str
    source_url: str
    status: str  # "revived" | "still_dead" | "error"
    http_code: Optional[int] = None
    error_msg: Optional[str] = None
    last_checked_at: str = ""

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "status": self.status,
            "http_code": self.http_code,
            "error_msg": self.error_msg,
            "last_checked_at": self.last_checked_at,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_threshold() -> int:
    """从 settings 表读 dead_for_days, 默认 7."""
    try:
        from backend.repository.db import get_connection
        conn = get_connection()
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            ("quality.revival_dead_for_days",),
        ).fetchone()
        if row and row["value"]:
            return max(1, int(row["value"]))
    except Exception as e:
        logger.debug(f"_read_threshold: {e}")
    return DEFAULT_DEAD_FOR_DAYS


def list_dead_sources(dead_for_days: int = DEFAULT_DEAD_FOR_DAYS) -> list[dict]:
    """返回所有 status='dead' AND last_checked_at < now - N days 的源.

    返回的 dict 来源自 source_stats repo, 字段:
    category / source_name / source_url / last_checked_at
    """
    from backend.repository.source_stats_repo import SourceStatsRepository

    repo = SourceStatsRepository()
    rows = repo.list_all()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=dead_for_days)).isoformat()
    out: list[dict] = []
    for r in rows:
        if str(r.get("status", "")) != "dead":
            continue
        last_checked = r.get("last_checked_at")
        if not last_checked or last_checked > cutoff:
            continue  # 死得不够久, 跳过
        out.append(
            {
                "category": str(r["category"]),
                "source_name": str(r["source_name"]),
                "source_url": str(r["source_url"]),
                "last_checked_at": str(last_checked),
            }
        )
    return out


def _check_url(url: str, timeout_s: float) -> tuple[int, Optional[str]]:
    """HEAD 请求 URL, 返回 (status_code, error_msg).

    200/3xx → 视为可达
    4xx/5xx → 不可达, 记录 error
    异常 (timeout / DNS / connection) → error_msg 非空
    """
    try:
        req = urllib.request.Request(url, method="HEAD")
        # 设 UA 避免被部分站点 403
        req.add_header("User-Agent", "hotspot/1.8 source-revival")
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            code = int(resp.status)
            return code, None
    except urllib.error.HTTPError as e:
        # 4xx/5xx 也是"可达但返回错误", 仍算 reachable
        return int(e.code), None
    except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
        return 0, f"{type(e).__name__}: {str(e)[:200]}"
    except Exception as e:
        return 0, f"{type(e).__name__}: {str(e)[:200]}"


def try_revive_one(
    category: str,
    source_name: str,
    source_url: str,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> RevivalResult:
    """尝试复活单条源.

    成功条件: HEAD 返回 2xx 或 3xx
    - 成功: DB 中该源 status='active', zero_yield_runs=0, last_checked_at=now
    - 失败: 标 status='dead' (保持), last_checked_at=now, last_error=err_msg
    """
    from backend.repository.source_stats_repo import SourceStatsRepository

    code, err = _check_url(source_url, timeout_s)
    repo = SourceStatsRepository()
    if err is None and 200 <= code < 400:
        # 复活: reset
        try:
            repo.reset(category, source_name)
            return RevivalResult(
                category=category,
                source_name=source_name,
                source_url=source_url,
                status="revived",
                http_code=code,
                last_checked_at=_now_iso(),
            )
        except Exception as e:
            return RevivalResult(
                category=category,
                source_name=source_name,
                source_url=source_url,
                status="error",
                http_code=code,
                error_msg=f"reset DB failed: {e}",
                last_checked_at=_now_iso(),
            )
    # 仍死 / 错误
    if err is None:
        # HTTP 错误码, 不复活
        return RevivalResult(
            category=category,
            source_name=source_name,
            source_url=source_url,
            status="still_dead",
            http_code=code,
            error_msg=f"HTTP {code}",
            last_checked_at=_now_iso(),
        )
    return RevivalResult(
        category=category,
        source_name=source_name,
        source_url=source_url,
        status="error",
        error_msg=err,
        last_checked_at=_now_iso(),
    )


def revive_all_dead(
    *,
    dead_for_days: Optional[int] = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> list[RevivalResult]:
    """对所有 dead 且死够久的源尝试复活.

    Returns
    -------
    list[RevivalResult]
        每条源的尝试结果 (revived / still_dead / error)
    """
    days = dead_for_days if dead_for_days is not None else _read_threshold()
    candidates = list_dead_sources(dead_for_days=days)
    if not candidates:
        logger.info(f"revive_all_dead: 0 candidates (dead_for_days={days})")
        return []
    logger.info(
        f"revive_all_dead: {len(candidates)} candidates (dead_for_days={days})"
    )
    results: list[RevivalResult] = []
    for c in candidates:
        r = try_revive_one(
            c["category"],
            c["source_name"],
            c["source_url"],
            timeout_s=timeout_s,
        )
        results.append(r)
    # 汇总
    revived = sum(1 for r in results if r.status == "revived")
    still = sum(1 for r in results if r.status == "still_dead")
    error = sum(1 for r in results if r.status == "error")
    logger.info(
        f"revive_all_dead: done. revived={revived} still_dead={still} error={error}"
    )
    return results


__all__ = [
    "list_dead_sources",
    "try_revive_one",
    "revive_all_dead",
    "RevivalResult",
    "DEFAULT_DEAD_FOR_DAYS",
    "DEFAULT_TIMEOUT_S",
]
