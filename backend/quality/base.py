"""质量门禁抽象基类 + 上下文。

每个具体门禁继承 :class:`BaseGate` 并实现 ``check()``。

约定
----
- ``check()`` **必须** 捕获所有内部异常并把错误信息写到
  ``GateResult.error_msg``；不应向上抛。
- 失败 = 扣分 + 打 flag；成功 = passed=True，零扣分。
- 扣分上限由具体门禁决定（schema=100，content=30/项，其他 15-50）。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel, Field

from backend.domain.collection import GateResult
from backend.domain.models import HotspotItem


class GateContext(BaseModel):
    """Per-pipeline-run context passed to each gate.

    Holds run-scoped state (e.g. existing URL set for duplicate
    detection, source reputation table, category keyword map). The
    context is built once by the pipeline and re-used for every item
    in a batch, so gates can amortise expensive lookups.
    """

    model_config = {"arbitrary_types_allowed": True}

    mode: str = "loose"  # "strict" / "loose"
    category_keywords: dict[str, list[str]] = Field(default_factory=dict)
    source_reputation: dict[str, dict[str, Any]] = Field(default_factory=dict)
    existing_urls: set[str] = Field(default_factory=set)
    existing_titles: list[str] = Field(default_factory=list)
    known_ids: Optional[Any] = None  # callable returning set of known ids
    http_session_factory: Optional[Any] = None  # callable returning aiohttp session


class BaseGate(ABC):
    """所有质量门禁的抽象基类。

    子类必须实现 :meth:`check`。
    """

    #: 门禁标识（"schema" / "content" / "category_match" / ...）。
    name: str = "base"

    @abstractmethod
    def check(
        self, item: HotspotItem, context: GateContext
    ) -> GateResult:
        """对单个 ``item`` 跑门禁。**不抛异常**。"""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # 公共辅助：包装异常
    # ------------------------------------------------------------------
    def _wrap_exception(self, item: HotspotItem, exc: Exception) -> GateResult:
        """把异常转成 ``GateResult(error_msg=...)``。

        门禁内部异常**不**扣分，仅把 ``error_msg`` 写到 log；
        调用方决定是否升级。
        """
        return GateResult(
            gate_name=self.name,
            passed=True,  # 失败不归咎于 item
            score_deduction=0,
            flags=[],
            error_msg=f"{type(exc).__name__}: {str(exc)[:200]}",
        )


__all__ = ["BaseGate", "GateContext"]
