"""URL Content gate — 异步抽样抓页面 + 关键词匹配。

- 抓页面 HTML 提取 ``<title>``
- 抓到的 ``<title>`` 与 item.title 重叠度 ≥ 30% 算"内容匹配"
- mismatch 扣 20 分，更新 ``url_check_status='mismatch'``
- 8s 超时
- 抽样（默认 10%）由调用方决定；本函数接受单 item。
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import aiohttp

from backend.config import config
from backend.domain.collection import GateResult
from backend.domain.models import HotspotItem
from backend.logging_config import logger
from backend.quality.base import BaseGate, GateContext
from backend.quality.title_summary_gate import _tokenize
from backend.utils.url_safety import (
    UrlSafetyError,
    safe_aiohttp_connector,
    validate_url,
)

_TITLE_RE = re.compile(
    r"<title[^>]*>(?P<title>[^<]+)</title>", re.IGNORECASE
)
_CONTENT_OVERLAP_THRESHOLD = 0.30


def _extract_title(html: str) -> str:
    """从 HTML 抽 ``<title>`` 内容；找不到返回空串。"""
    if not html:
        return ""
    m = _TITLE_RE.search(html)
    return m.group("title").strip() if m else ""


async def _fetch_title(
    url: str, timeout: int
) -> tuple[str, str | None]:
    """``(title, error)``。``error`` 非空表示抓取失败。

    v0.8.6 P0-9 / 审计 F0-11 (R6): 正文抓取此前裸 ``session.get(url,
    ssl=False)`` — 无 SSRF 校验 (item.url 可控, 可探内网读回响应) 且
    禁用 TLS 校验 (MITM)。现走全仓唯一出站校验源 ``utils/url_safety``:

    1. ``validate_url`` 前置拒收 (loopback/私网/保留段/非 http(s) scheme),
       DNS 解析到私网 IP 同样拒 — 错误串以 ``SSRF blocked`` 开头;
    2. ``safe_aiohttp_connector`` 锁解析 IP 防 DNS rebinding;
    3. **不再传 ``ssl=False``** — TLS 证书校验默认开启 (ssl=True)。
    """
    try:
        validate_url(url)
    except UrlSafetyError as e:
        return "", f"SSRF blocked: {e}"
    connector: aiohttp.TCPConnector | None = None
    try:
        host = urlparse(url).hostname or ""
        connector = safe_aiohttp_connector(host, ssl=True)
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(
            timeout=client_timeout, connector=connector
        ) as session, session.get(
            url,
            headers={"User-Agent": "hotspot-quality/1.0"},
        ) as resp:
            connector = None  # session 关闭时负责关闭 connector
            if resp.status >= 400:
                return "", f"HTTP {resp.status}"
            # 只读 64KB 足以拿到 <title>
            body = await resp.content.read(64 * 1024)
            html = body.decode("utf-8", errors="ignore")
            return _extract_title(html), None
    except Exception as e:
        return "", f"{type(e).__name__}: {str(e)[:100]}"
    finally:
        if connector is not None:
            # Session 构造失败等早退路径, connector 未被 session 接管
            await connector.close()


class URLContentGate(BaseGate):
    """URL 内容验证门禁（异步跑）。"""

    name = "url_content"

    def __init__(self, timeout: int | None = None):
        self.timeout = timeout or config.quality_url_check_timeout

    def check(
        self, item: HotspotItem, context: GateContext
    ) -> GateResult:
        # 同步入口：fallback 调用方应走 ``run_async()`` 拿到真实结果。
        # 这里返回"未执行"标记，不扣分。
        return GateResult(
            gate_name=self.name,
            passed=True,
            score_deduction=0,
            flags=[],
            reason="async gate, see run_async()",
        )

    async def run_async(
        self, item: HotspotItem
    ) -> GateResult:
        """异步执行：抓页面 + 计算 title 重叠度。"""
        try:
            page_title, error = await _fetch_title(
                str(item.url), self.timeout
            )
            if error or not page_title:
                logger.info(
                    "url_content fetch failed",
                    extra={
                        "trace_id": "",
                        "item_id": item.id,
                        "url": str(item.url)[:120],
                        "error": error,
                    },
                )
                # P0-9/F0-11: SSRF 阻断专属 flag — 审计验收 "内网用例被阻断"
                # 需要可在 quality_check_logs 里区分的标记, 不能混入普通不可达
                ssrf = bool(error) and error.startswith("SSRF blocked")
                return GateResult(
                    gate_name=self.name,
                    passed=False,
                    score_deduction=20,
                    flags=["ssrf_blocked"] if ssrf else ["url_unreachable"],
                    reason=f"fetch failed: {error}",
                )

            item_tokens = _tokenize(item.title)
            page_tokens = _tokenize(page_title)
            if not item_tokens or not page_tokens:
                # 抽取不到分词不扣分
                return GateResult(
                    gate_name=self.name,
                    passed=True,
                    score_deduction=0,
                    flags=[],
                    reason="empty tokens",
                )

            intersection = item_tokens & page_tokens
            union = item_tokens | page_tokens
            overlap = len(intersection) / max(1, len(union))

            if overlap >= _CONTENT_OVERLAP_THRESHOLD:
                return GateResult(
                    gate_name=self.name,
                    passed=True,
                    score_deduction=0,
                    flags=[],
                    reason=f"overlap={overlap:.2%}",
                )

            return GateResult(
                gate_name=self.name,
                passed=False,
                score_deduction=20,
                flags=["url_mismatch"],
                reason=(
                    f"page title '{page_title[:50]}' overlap="
                    f"{overlap:.2%} < "
                    f"{_CONTENT_OVERLAP_THRESHOLD:.0%}"
                ),
            )
        except Exception as e:
            return self._wrap_exception(item, e)


__all__ = ["URLContentGate"]
