"""S1-3 书签存活三态检测 (docs/HOTSPOT_SECNEWS_INTEGRATION.md §7.1)。

对 bookmark-import 来源的 item 的 url 做 HEAD(+GET 兜底) 探测, 把三态写回
frontmatter: alive = alive / dead / unknown。探测永不抛异常 — 网络层一切
失败要么归 dead (明确不可达: DNS 不存在/连接拒绝/HTTP>=400), 要么归
unknown (超时等无法判定的瞬态)。每周日 02:00 UTC 由调度器批扫一次。
"""

from __future__ import annotations

import logging
import socket
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.wiki_fs.store import WikiFs

logger = logging.getLogger(__name__)

ALIVE_STATES = ("alive", "dead", "unknown")

# 命中任一 source 的 item 才参与存活扫描 (书签导入链路)
_BOOKMARK_SOURCES = ("bookmark-import", "bookmark")

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _extract_url(fm: dict) -> str:
    for key in ("url", "source_url"):
        v = fm.get(key)
        if isinstance(v, str) and v.startswith(("http://", "https://")):
            return v
    return ""


def check_url(url: str, timeout: float = 10.0) -> str:
    """探测单个 URL, 返回 alive/dead/unknown。永不抛异常。

    规则 (§7.1): HEAD 失败且服务端拒绝该方法 (405/501) 时降级 GET 重试;
    HTTP >= 400 或 DNS 不存在/连接拒绝 → dead; 超时等瞬态 → unknown。
    """
    if not url:
        return "unknown"
    try:
        return _probe(url, timeout)
    except Exception:  # noqa: BLE001 — 三态契约要求任何异常都收敛为 unknown
        return "unknown"


def _probe(url: str, timeout: float) -> str:
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(
            url, method=method, headers={"User-Agent": _UA}
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = getattr(resp, "status", resp.getcode())
                return "alive" if status < 400 else "dead"
        except urllib.error.HTTPError as e:
            # 405/501 = 服务器不支持 HEAD → 换 GET 再试; 其余 4xx/5xx 即 dead
            if e.code in (405, 501) and method == "HEAD":
                continue
            return "dead"
        except (urllib.error.URLError, TimeoutError) as e:
            reason = getattr(e, "reason", e)
            if isinstance(reason, (socket.timeout, TimeoutError)):
                return "unknown"
            if isinstance(reason, ConnectionResetError):
                return "unknown"
            # DNS 解析失败 / 连接拒绝 → 目标确定不可达
            return "dead"
        except OSError as e:
            if isinstance(e, (socket.timeout, TimeoutError)):
                return "unknown"
            return "dead"
    return "unknown"


def sweep_liveness(
    wiki_fs: "WikiFs",
    *,
    limit: int | None = None,
    workers: int = 16,
    timeout: float = 10.0,
) -> dict:
    """批扫全部书签来源 item, 写回 alive/alive_checked_at。返回三态计数。"""
    targets: list[tuple[str, str]] = []
    for item_id in wiki_fs.list_ids():
        try:
            item = wiki_fs.read_item(item_id)
        except Exception as e:  # noqa: BLE001 — 单条损坏不阻断批扫
            logger.warning(f"sweep_liveness: skip unreadable {item_id}: {e}")
            continue
        fm = item.get("fm", {})
        src = fm.get("source", "")
        if src not in _BOOKMARK_SOURCES:
            continue
        url = _extract_url(fm)
        if url:
            targets.append((item_id, url))
        if limit is not None and len(targets) >= limit:
            break

    counts = {"total": len(targets), "alive": 0, "dead": 0, "unknown": 0}
    if not targets:
        return counts

    def _check(pair: tuple[str, str]) -> tuple[str, str]:
        item_id, url = pair
        return item_id, check_url(url, timeout=timeout)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for item_id, state in pool.map(_check, targets):
            counts[state] += 1
            try:
                item = wiki_fs.read_item(item_id)
                fm = dict(item.get("fm", {}))
                fm["alive"] = state
                fm["alive_checked_at"] = datetime.now(timezone.utc).isoformat()
                wiki_fs.write_item(item_id, {"fm": fm, "body": item.get("body", "")})
            except Exception as e:  # noqa: BLE001 — 写回失败降级为 unknown 口径外损失
                counts[state] -= 1
                counts["unknown"] += 1
                logger.warning(f"sweep_liveness: write-back failed {item_id}: {e}")

    logger.info(f"sweep_liveness: {counts}")
    return counts


def liveness_counts(wiki_fs: "WikiFs") -> dict:
    """只读统计当前 frontmatter 中的三态分布 (观测台 S1-4 用, 零网络 IO)。"""
    counts = {"total": 0, "alive": 0, "dead": 0, "unknown": 0}
    for item_id in wiki_fs.list_ids():
        try:
            fm = wiki_fs.read_item(item_id).get("fm", {})
        except Exception:  # noqa: BLE001
            continue
        if fm.get("source", "") not in _BOOKMARK_SOURCES:
            continue
        counts["total"] += 1
        state = fm.get("alive", "unknown")
        if state not in ALIVE_STATES:
            state = "unknown"
        counts[state] += 1
    return counts


__all__ = ["ALIVE_STATES", "check_url", "liveness_counts", "sweep_liveness"]
