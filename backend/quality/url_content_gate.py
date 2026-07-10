"""URL Content gate — 异步抽样抓页面 + 关键词匹配。

- 抓页面 HTML 提取 ``<title>``
- 抓到的 ``<title>`` 与 item.title 重叠度 ≥ 30% 算"内容匹配"
- mismatch 扣 20 分，更新 ``url_check_status='mismatch'``
- 8s 超时
- 抽样（默认 10%）由调用方决定；本函数接受单 item。
"""
from __future__ import annotations

import re
from typing import Optional

import aiohttp

from backend.config import config
from backend.domain.collection import GateResult
from backend.domain.models import HotspotItem
from backend.logging_config import logger
from backend.quality.base import BaseGate, GateContext
from backend.quality.title_summary_gate import _tokenize

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
) -> tuple[str, Optional[str]]:
    """``(title, error)``。``error`` 非空表示抓取失败。"""
    try:
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.get(
                url,
                headers={"User-Agent": "hotspot-quality/1.0"},
                ssl=False,
            ) as resp:
                if resp.status >= 400:
                    return "", f"HTTP {resp.status}"
                # 只读 64KB 足以拿到 <title>
                body = await resp.content.read(64 * 1024)
                html = body.decode("utf-8", errors="ignore")
                return _extract_title(html), None
    except Exception as e:
        return "", f"{type(e).__name__}: {str(e)[:100]}"


class URLContentGate(BaseGate):
    """URL 内容验证门禁（异步跑）。"""

    name = "url_content"

    def __init__(self, timeout: Optional[int] = None):
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
                return GateResult(
                    gate_name=self.name,
                    passed=False,
                    score_deduction=20,
                    flags=["url_unreachable"],
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
