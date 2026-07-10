"""Schema gate — 重新跑 Pydantic v2 校验 ``HotspotItem``。

- 失败 → flag ``schema_invalid``，扣 100 分（实质拒绝）
- 通过 → passed=True，零扣分
"""
from __future__ import annotations

from pydantic import ValidationError

from backend.domain.collection import GateResult
from backend.domain.models import HotspotItem
from backend.quality.base import BaseGate, GateContext


class SchemaGate(BaseGate):
    """Pydantic 二次校验门禁。"""

    name = "schema"

    def check(
        self, item: HotspotItem, context: GateContext
    ) -> GateResult:
        try:
            # ``model_validate`` 等价于重建实例。
            # ``from_attributes`` 对 Pydantic 数据类对象使用；
            # 我们的 HotspotItem 是 BaseModel, dict 形式可走 model_validate。
            HotspotItem.model_validate(item.model_dump(mode="json"))
            return GateResult(
                gate_name=self.name,
                passed=True,
                score_deduction=0,
                flags=[],
            )
        except ValidationError as e:
            return GateResult(
                gate_name=self.name,
                passed=False,
                score_deduction=100,
                flags=["schema_invalid"],
                reason=f"validation failed: {e.errors()[:3]}",
            )
        except Exception as e:
            return self._wrap_exception(item, e)


__all__ = ["SchemaGate"]
