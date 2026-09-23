"""死源探活服务 — 对 dead 源执行 HEAD/GET 探测，恢复后入 grace 状态。

Phase 3: 每日 03:30 Asia/Shanghai 对 dead 源执行探测。

v0.7.x P0: SSRF 防护 — ``_head_status`` / ``_get_status`` 在出站前
走 ``validate_url``,阻断 localhost / 环回 / 私网 / 保留 IP。
"""
from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.logging_config import logger as _root_logger
from backend.repository.db import get_connection
from backend.repository.source_scheduler_repo import SourceSchedulerRepository
from backend.utils.url_safety import UrlSafetyError, safe_urllib_request, validate_url

logger = _root_logger.bind(component="source_prober")

DEFAULT_TIMEOUT_S = 10.0
_UA = "hotspot-source-prober/3.0"


@dataclass
class ProbeResult:
    """单条源的探测结果。"""
    source_id: str
    url: str
    status: str  # "alive" | "dead" | "error"
    http_code: int = 0
    error_msg: str | None = None
    new_status: str | None = None  # 'grace' if alive, None if still dead

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "url": self.url,
            "status": self.status,
            "http_code": self.http_code,
            "error_msg": self.error_msg,
            "new_status": self.new_status,
        }


def _head_status(url: str, timeout: int) -> tuple[int, str | None]:
    """HEAD 请求，返回 (status_code, error_msg)。

    v0.7.x P0: SSRF 校验 — ``crawler_sources`` 行是 admin 注入的,
    但允许内网/环回 host 进入仍是越权 (probe 服务在 8000 端口,
    ``UrlSafetyError`` 应阻断任意"探自家服务"的尝试)。
    """
    try:
        validate_url(url)
    except UrlSafetyError as e:
        return 0, f"ssrf_block: {str(e)[:200]}"
    try:
        req = safe_urllib_request(url, method="HEAD", timeout=timeout)
        req.add_header("User-Agent", _UA)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), None
    except urllib.error.HTTPError as e:
        # 405/501 → fallback to GET in caller
        return int(e.code), None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, f"{type(e).__name__}: {str(e)[:200]}"
    except Exception as e:
        return 0, f"{type(e).__name__}: {str(e)[:200]}"


def _get_status(url: str, timeout: int) -> tuple[int, str | None]:
    """GET 请求，返回 (status_code, error_msg)。"""
    try:
        validate_url(url)
    except UrlSafetyError as e:
        return 0, f"ssrf_block: {str(e)[:200]}"
    try:
        req = safe_urllib_request(url, method="GET", timeout=timeout)
        req.add_header("User-Agent", _UA)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), None
    except urllib.error.HTTPError as e:
        return int(e.code), None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, f"{type(e).__name__}: {str(e)[:200]}"
    except Exception as e:
        return 0, f"{type(e).__name__}: {str(e)[:200]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_dead_sources() -> list[dict]:
    """查询 crawler_sources 中 status='dead' AND enabled=1 的源。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, url, feed_url, api_url FROM crawler_sources "
        "WHERE status = 'dead' AND enabled = 1"
    ).fetchall()
    return [dict(r) for r in rows]


def _get_probe_url(source: dict) -> str:
    """获取探测 URL: feed_url > url > api_url。"""
    return source.get("feed_url") or source.get("url") or source.get("api_url") or ""


def probe_one(
    source_id: str,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    produced_items: int = 0,
) -> ProbeResult:
    """探测单个 dead 源。

    1. 查找 crawler_sources 行
    2. 获取探测 URL（feed_url > url > api_url）
    3. HEAD 请求，超时 10s
    4. HEAD 405/501 → fallback 到 GET
    5. 2xx/3xx → status='grace', consecutive_failures=0
    6. 4xx/5xx → 保留 dead, 更新 last_error

    采集闭环 T1 (yield 口径): 探测只是连通性检查, 本身零产出 — 默认
    **不抬** ``last_yield_at``/``last_success_at`` (历史实现在 alive 路径
    无条件刷新两时间戳, hotspots 无新行, yield 口径被探测污染)。仅当调用
    方确认本次探测运行有真实条目入库 (``produced_items > 0``) 时才抬。

    Args:
        source_id: crawler_sources.id
        timeout_s: 探测超时秒数
        produced_items: 本次探测运行真实入库的 hotspots 新行数 (HEAD
            连通性探测恒为 0; 探测后附带真实抓取时由调用方传入)

    Returns:
        ProbeResult
    """
    repo = SourceSchedulerRepository()
    source = repo.get_by_id(source_id)
    if source is None:
        return ProbeResult(
            source_id=source_id,
            url="",
            status="error",
            error_msg="source not found in crawler_sources",
        )
    
    url = _get_probe_url(source)
    if not url:
        return ProbeResult(
            source_id=source_id,
            url="",
            status="error",
            error_msg="no URL configured for source",
        )
    
    code, err = _head_status(url, int(timeout_s))
    
    # HEAD 405/501 → fallback to GET
    if code in (405, 501) or (code == 0 and err and "HTTPError" in err):
        code, err = _get_status(url, int(timeout_s))
    
    if err is None and 200 <= code < 400:
        # Alive → grace。零产出不抬 yield/success 时间戳 (采集闭环 T1);
        # last_error 成功路径存 NULL 清空旧错误。
        alive_fields: dict = {
            "status": "grace",
            "consecutive_failures": 0,
            "last_error": None,
            "grace_rounds": 0,
            "cooldown_until": None,
        }
        if produced_items > 0:
            now = _now_iso()
            alive_fields["last_yield_at"] = now
            alive_fields["last_success_at"] = now
        repo.update_health_state(source_id, **alive_fields)
        logger.info(
            f"source {source_id} ({source.get('name', '')}) probed alive "
            f"(HTTP {code}), moving to grace "
            f"(yield_bumped={produced_items > 0})"
        )
        return ProbeResult(
            source_id=source_id,
            url=url,
            status="alive",
            http_code=code,
            new_status="grace",
        )
    
    # Still dead
    error_msg = err or f"HTTP {code}"
    repo.update_health_state(
        source_id,
        last_error=error_msg[:200],
    )
    logger.info(
        f"source {source_id} ({source.get('name', '')}) probed dead "
        f"(HTTP {code}), keeping dead"
    )
    return ProbeResult(
        source_id=source_id,
        url=url,
        status="dead",
        http_code=code,
        error_msg=error_msg,
        new_status="dead",
    )


def probe_all_dead(*, timeout_s: float = DEFAULT_TIMEOUT_S) -> list[dict]:
    """探测所有 dead 源。
    
    Returns:
        list[dict]: 每条源的探测结果
    """
    sources = list_dead_sources()
    if not sources:
        logger.info("probe_all_dead: no dead sources to probe")
        return []
    
    logger.info(f"probe_all_dead: probing {len(sources)} dead sources")
    results: list[dict] = []
    for source in sources:
        try:
            result = probe_one(source["id"], timeout_s=timeout_s)
            results.append(result.to_dict())
        except Exception as e:
            logger.error(f"probe_all_dead: source {source['id']} crashed: {e}")
            results.append({
                "source_id": source["id"],
                "url": _get_probe_url(source),
                "status": "error",
                "http_code": 0,
                "error_msg": f"{type(e).__name__}: {str(e)[:200]}",
                "new_status": None,
            })
    
    alive = sum(1 for r in results if r["status"] == "alive")
    dead = sum(1 for r in results if r["status"] == "dead")
    error = sum(1 for r in results if r["status"] == "error")
    logger.info(
        f"probe_all_dead: done. alive={alive} dead={dead} error={error}"
    )
    return results


__all__ = [
    "DEFAULT_TIMEOUT_S",
    "ProbeResult",
    "list_dead_sources",
    "probe_all_dead",
    "probe_one",
]