"""URL Validity gate — 同步 urllib 检查 URL 可达性。

- 2xx/3xx → 通过
- 4xx/5xx/超时/连接失败 → passed=False, flag ``url_unreachable``, 扣 25 分
- timeout 5s

实现要点
--------
- 用 ``urllib.request`` 同步发请求，不引 aiohttp 依赖（避免事件循环冲突）。
- 调用方 ``BaseCollector._run_quality_gates`` 通过 ``asyncio.to_thread`` 把整个
  pipeline 放到 thread pool 跑，所以这里的 sync urllib **不会**阻塞 event loop。
- 部分站点不支持 ``HEAD``（返回 405/501），自动 fallback 到 ``GET``。
"""
from __future__ import annotations

import urllib.error
import urllib.request

from backend.domain.collection import GateResult
from backend.domain.models import HotspotItem
from backend.quality.base import BaseGate, GateContext

_TIMEOUT_SECONDS = 5
_PENALTY = 25
_UA = "hotspot-quality/1.0"


def _head_status(url: str, timeout: int) -> int:
    """同步 HEAD 请求, 返回 HTTP status。"""
    req = urllib.request.Request(
        url, method="HEAD", headers={"User-Agent": _UA}
    )
    resp = urllib.request.urlopen(req, timeout=timeout)
    return resp.status


def _get_status(url: str, timeout: int) -> int:
    """同步 GET 请求, 返回 HTTP status。"""
    req = urllib.request.Request(
        url, method="GET", headers={"User-Agent": _UA}
    )
    resp = urllib.request.urlopen(req, timeout=timeout)
    return resp.status


class URLValidityGate(BaseGate):
    """URL 可达性门禁。"""

    name = "url_validity"

    def __init__(self, timeout: int = _TIMEOUT_SECONDS):
        self.timeout = timeout

    def check(
        self, item: HotspotItem, context: GateContext
    ) -> GateResult:
        url = str(item.url)
        try:
            try:
                status = _head_status(url, self.timeout)
            except urllib.error.HTTPError as e:
                # 405 Method Not Allowed / 501 Not Implemented → fallback GET
                if e.code in (405, 501):
                    try:
                        status = _get_status(url, self.timeout)
                    except urllib.error.HTTPError as e2:
                        status = e2.code
                else:
                    status = e.code
        except Exception as e:
            return GateResult(
                gate_name=self.name,
                passed=False,
                score_deduction=_PENALTY,
                flags=["url_unreachable"],
                reason=f"url_unreachable: {type(e).__name__}: {str(e)[:80]}",
            )

        if 200 <= status < 400:
            return GateResult(
                gate_name=self.name,
                passed=True,
                score_deduction=0,
                flags=[],
            )
        return GateResult(
            gate_name=self.name,
            passed=False,
            score_deduction=_PENALTY,
            flags=["url_unreachable"],
            reason=f"url_unreachable: HTTP {status}",
        )


__all__ = ["URLValidityGate"]
