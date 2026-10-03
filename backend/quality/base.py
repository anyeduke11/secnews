"""质量门禁抽象基类 + 上下文。

每个具体门禁继承 :class:`BaseGate` 并实现 ``check()``。

约定
----
- ``check()`` 内部异常应通过 :meth:`BaseGate._wrap_exception` 转成
  fail-closed 的 ``GateResult``（不冒充通过）；也可直接上抛, 由
  pipeline 同构兜底 —— 两条路径结论必须一致 (E13/P0-12)。
- 失败 = 扣分 + 打 flag；成功 = passed=True，零扣分。
- 扣分上限由具体门禁决定（schema=100，content=30/项，其他 15-50）。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Literal

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
    known_ids: Any | None = None  # callable returning set of known ids
    http_session_factory: Any | None = None  # callable returning aiohttp session
    rejected_by: str | None = None  # 首个失败的 Hard gate 名称
    # v4.4: LLM AI 生成检测配置（由 pipeline 构建时注入，避免 gate 查 DB）
    llm_enabled: bool = False
    llm_provider: str = "sensenova"  # "sensenova" | "ollama"
    llm_api_key: str = ""


class BaseGate(ABC):
    """所有质量门禁的抽象基类。

    子类必须实现 :meth:`check`。
    """

    #: 门禁标识（"schema" / "content" / "category_match" / ...）。
    name: str = "base"

    #: 门禁类型: "hard" 表示拒绝性门禁, "soft" 表示评分性门禁。
    gate_type: ClassVar[Literal["hard", "soft"]] = "soft"

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
        """把门禁内部异常转成 fail-closed 的 ``GateResult``。

        E13/P0-12: 与 ``QualityGatePipeline._check_gate`` 的兜底结论**完全
        一致** — 门禁崩溃不得冒充通过 (此前 passed=True/零扣分等于免检放行,
        任何 gate 代码缺陷都会让该关静默全开)。统一语义:
        ``passed=False`` + ``gate_crashed`` flag + 扣 15 分 + error_msg。
        strict 模式因此拒绝; loose 模式打标扣分仍入库, 崩溃在质量面板可见。

        本方法是两条异常路径 (gate 内自捕 / 上抛被 pipeline 捕获) 的**唯一
        结果构造点**, 防止错误策略再次分叉。
        """
        detail = f"{type(exc).__name__}: {str(exc)[:200]}"
        return GateResult(
            gate_name=self.name,
            passed=False,
            score_deduction=15,
            flags=["gate_crashed"],
            reason=f"gate crashed: {detail}",
            error_msg=detail,
        )


__all__ = ["BaseGate", "GateContext"]
