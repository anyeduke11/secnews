"""Phase 9.2 最终 URL 下钻门禁

对 :class:`HotspotItem` 的 ``url`` 字段做二次下钻：landing 页（tag/搜索/作者/分类）
→ 真实文章 URL。

触发场景
--------
用户截图反馈：qbitai.com 等 AI 资讯源 RSS 抓到的 URL 是 ``/tag/worldclaw`` 这类
标签聚合页，点击卡片跳到标签页而非真实文章。本门禁在 quality pipeline 中自动检测
这种 URL，抓页面 HTML 抽取第一个真实文章 URL，替换 ``item.url`` 并写回。

判定与扣分
----------
- 已是真实文章 URL → passed=True，无扣分无 flag
- 是 landing 页且下钻成功 → passed=True，**不扣分**（门禁完成了工作）
  + flag ``url_drilldown_resolved`` + flag ``url_drilldown_from=<原 url>``
  + 直接修改 ``item.url`` 替换为真实文章 URL
- 是 landing 页但下钻失败 → passed=False，扣 5 分 + flag ``url_drilldown_failed``
- 整个 URL 是 mailto: 等无法处理 → passed=False，扣 8 分（提示"垃圾数据"）
  + flag ``url_not_drillable``
- 抓取异常 / 超时 → passed=False，扣 3 分 + flag ``url_drilldown_error``（网络问题）
- 在事件循环中调用 → passed=True + flag ``url_drilldown_skipped_loop``
  （避免 sync urllib 阻塞 event loop；运维可通过脚本在非 loop 上下文重跑下钻）

异步运行
--------
默认走 sync urllib（与 ``url_validity_gate`` 一致），timeout 3s。
调用方应在 event loop 上下文中改用 :func:`run_final_url_gate_async` 把
``gate.check`` 放到 thread pool 跑。
"""
from __future__ import annotations

import asyncio

from backend.domain.collection import GateResult
from backend.domain.models import HotspotItem
from backend.quality.base import BaseGate, GateContext
from backend.quality.final_url_resolver import (
    is_landing_page,
    resolve_final_url,
)


REWARD_OK = 0
PENALTY_FAILED = 5
PENALTY_NOT_DRILLABLE = 8
PENALTY_ERROR = 3


def _in_event_loop() -> bool:
    """检查当前是否在 asyncio event loop 中（避免 sync urllib 阻塞）。"""
    try:
        loop = asyncio.get_event_loop()
        return loop.is_running()
    except RuntimeError:
        return False


class FinalUrlGate(BaseGate):
    """对 item.url 做下钻：landing 页 → 真实文章 URL。

    该 gate 内部直接修改 ``item.url`` 字段，后续 pipeline 末尾的
    ``model_copy(update=...)`` 只覆盖 quality 字段 → url 修改被保留。
    """

    name: str = "FinalUrl"

    def __init__(self, *, fetch_timeout: float = 3.0):
        self._fetch_timeout = fetch_timeout

    def check(self, item: HotspotItem, context: GateContext) -> GateResult:
        original_url = str(item.url or "")
        # 1. URL 已是真实文章 → 跳过
        if not is_landing_page(original_url):
            return GateResult(
                gate_name=self.name,
                passed=True,
                score_deduction=REWARD_OK,
                flags=[],
                reason="url_already_final",
            )
        # 2. mailto: 等无法处理
        if original_url.startswith("mailto:"):
            return GateResult(
                gate_name=self.name,
                passed=False,
                score_deduction=PENALTY_NOT_DRILLABLE,
                flags=["url_not_drillable", "url_not_drillable_kind=mailto"],
                reason=f"url_not_drillable: mailto link {original_url[:60]}",
            )
        # 3. 同步下钻（已用 urllib 内部，3 秒超时）
        try:
            resolved = resolve_final_url(original_url)
        except Exception as exc:  # 网络异常等
            return GateResult(
                gate_name=self.name,
                passed=False,
                score_deduction=PENALTY_ERROR,
                flags=["url_drilldown_error", f"url_drilldown_error_kind={type(exc).__name__}"],
                reason=f"url_drilldown_error: {type(exc).__name__}: {exc}",
            )
        # 4. 抓取/解析失败
        if resolved is None:
            return GateResult(
                gate_name=self.name,
                passed=False,
                score_deduction=PENALTY_FAILED,
                flags=["url_drilldown_failed"],
                reason=f"url_drilldown_failed: no article URL found in landing page {original_url[:60]}",
            )
        # 5. 抓到原 URL 自己（域名没在 registry，无可下钻模式）
        if resolved == original_url:
            return GateResult(
                gate_name=self.name,
                passed=True,
                score_deduction=REWARD_OK,
                flags=["url_drilldown_no_pattern", f"url_drilldown_from={original_url}"],
                reason="url_drilldown_no_pattern: domain not registered, kept original",
            )
        # 6. 成功下钻 → 替换 item.url
        item.url = resolved
        # 写 flag 供溯源
        short_from = original_url[:60]
        return GateResult(
            gate_name=self.name,
            passed=True,
            score_deduction=REWARD_OK,
            flags=[
                "url_drilldown_resolved",
                f"url_drilldown_from={short_from}",
                f"url_drilldown_to={resolved}",
            ],
            reason=f"url_drilldown_resolved: {short_from} -> {resolved}",
        )


# ----------------------------------------------------------------------------
# 异步辅助：放到 thread pool 跑，避免阻塞 event loop
# ----------------------------------------------------------------------------
async def run_final_url_gate_async(gate: FinalUrlGate, item, context) -> GateResult:
    """异步包装：把同步 urllib 抓取放到 thread pool。"""
    return await asyncio.to_thread(gate.check, item, context)


__all__ = ["FinalUrlGate", "run_final_url_gate_async"]
