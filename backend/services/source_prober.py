"""死源探活服务 — 对 dead 源执行 HEAD/GET 探测，恢复后入 grace 状态。

Phase 3: 每日 03:30 Asia/Shanghai 对 dead 源执行探测。

v0.7.x P0: SSRF 防护 — ``_head_status`` / ``_get_status`` 在出站前
走 ``validate_url``,阻断 localhost / 环回 / 私网 / 保留 IP。

采集闭环 T3 (owner 裁决②): 失效源自动退役闭环 —
- dead 且死亡持续 >14 天且本轮探测失败 → enabled=0, status='retired'
  + source_alerts(source_retired, P1);
- retired 源降频复探 (复探冷却 7 天, 借用 cooldown_until 列存"下次
  可复探时刻"), 探测成功 → enabled=1, status='grace' + source_revived。
"""
from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from backend.logging_config import logger as _root_logger
from backend.repository.db import get_connection
from backend.repository.source_alert_repo import SourceAlertRepository
from backend.repository.source_scheduler_repo import SourceSchedulerRepository
from backend.utils.url_safety import UrlSafetyError, safe_urllib_request, validate_url

logger = _root_logger.bind(component="source_prober")

DEFAULT_TIMEOUT_S = 10.0
_UA = "hotspot-source-prober/3.0"

# 采集闭环 T3: dead 持续超过该天数且当日探测失败 → 自动退役
RETIRE_DEAD_DAYS = 14
# retired 源复探间隔 (低频, 防长期打死亡源); 借用 cooldown_until 存下次可复探时刻
RETIRE_REPROBE_DAYS = 7


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


def _parse_ts(ts: object) -> datetime | None:
    """ISO 时间串 → aware datetime; 解析失败返回 None。"""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _death_started_at(source: dict) -> datetime | None:
    """死亡起点口径 (采集闭环 T3)。

    crawler_sources 无"进入 dead 时刻"列; 以 last_success_at (最后一次
    真实产出, 天然早于判死时刻) 为死亡起点代理, 从未产出过的源回退
    created_at (注册即死)。两者皆无 → None (保守不退役)。
    """
    return _parse_ts(source.get("last_success_at")) or _parse_ts(
        source.get("created_at")
    )


def _death_days(source: dict) -> float | None:
    """死亡持续天数; 起点不可知时返回 None (不退役)。"""
    start = _death_started_at(source)
    if start is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - start).total_seconds() / 86400)


def _reprobe_due_iso() -> str:
    """retired 源下次可复探时刻 (now + RETIRE_REPROBE_DAYS)。"""
    return (
        datetime.now(timezone.utc) + timedelta(days=RETIRE_REPROBE_DAYS)
    ).isoformat()


def _write_retire_alert(source: dict, death_days: float) -> None:
    """写/推新 source_retired 告警 (P1, 走 upsert_dedup 防同类重复积累)。"""
    SourceAlertRepository().upsert_dedup({
        "source_id": str(source["id"]),
        "alert_type": "source_retired",
        "level": "P1",
        "message": (
            f"源 {source.get('name', source['id'])} 死亡 {death_days:.0f} 天"
            f"仍未复活, 已自动退役 (retired)"
        ),
        "detail": (
            f'{{"death_days": {death_days:.1f}, '
            f'"last_success_at": {str(source.get("last_success_at"))!r}}}'
        ),
    })


def _write_revive_alert(source: dict) -> None:
    """写/推新 source_revived 告警 (retired 源探测成功恢复采集)。"""
    SourceAlertRepository().upsert_dedup({
        "source_id": str(source["id"]),
        "alert_type": "source_revived",
        "level": "P2",
        "message": (
            f"源 {source.get('name', source['id'])} 探测复活成功, "
            f"已恢复采集 (grace)"
        ),
        "detail": '{"prev_status": "retired"}',
    })


def list_dead_sources() -> list[dict]:
    """查询待探测源 (采集闭环 T3 扩展)。

    - status='dead' AND enabled=1: 每日探测;
    - status='retired': 降频复探 — 仅当 cooldown_until (下次可复探时刻)
      为空或已过期时纳入, 实现每周一次而非每日。
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM crawler_sources "
        "WHERE (status = 'dead' AND enabled = 1) "
        "   OR (status = 'retired' AND (cooldown_until IS NULL "
        "       OR julianday(cooldown_until) < julianday('now')))"
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

    prev_status = str(source.get("status", ""))
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
        # 采集闭环 T3: retired 源探测成功 → 重新启用 + 记录复活告警
        if prev_status == "retired":
            alive_fields["enabled"] = 1
            _write_revive_alert(source)
            logger.info(
                f"source {source_id} ({source.get('name', '')}) revived "
                f"from retired (HTTP {code})"
            )
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
    failed_fields: dict = {
        "last_error": error_msg[:200],
    }

    # 采集闭环 T3: 退役闭环
    if prev_status == "dead":
        death_days = _death_days(source)
        if death_days is not None and death_days > RETIRE_DEAD_DAYS:
            # dead 且死亡 >14d 且本轮探测失败 → 自动退役
            failed_fields.update(
                status="retired",
                enabled=0,
                cooldown_until=_reprobe_due_iso(),
            )
            _write_retire_alert(source, death_days)
            logger.warning(
                f"source {source_id} ({source.get('name', '')}) retired: "
                f"dead for {death_days:.0f}d > {RETIRE_DEAD_DAYS}d "
                f"and probe failed (HTTP {code})"
            )
    elif prev_status == "retired":
        # retired 复探仍失败 → 保持退役, 重新武装 7 天复探冷却 (低频)
        failed_fields["cooldown_until"] = _reprobe_due_iso()
        _write_retire_alert(source, _death_days(source) or 0.0)

    repo.update_health_state(source_id, **failed_fields)
    # 状态汇报: 退役成功 → retired; retired 复探失败保持 retired; 其余 dead
    new_status = (
        "retired"
        if failed_fields.get("status") == "retired" or prev_status == "retired"
        else "dead"
    )
    logger.info(
        f"source {source_id} ({source.get('name', '')}) probed dead "
        f"(HTTP {code}), keeping {new_status}"
    )
    return ProbeResult(
        source_id=source_id,
        url=url,
        status="dead",
        http_code=code,
        error_msg=error_msg,
        new_status=new_status,
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
    "RETIRE_DEAD_DAYS",
    "RETIRE_REPROBE_DAYS",
    "ProbeResult",
    "list_dead_sources",
    "probe_all_dead",
    "probe_one",
]