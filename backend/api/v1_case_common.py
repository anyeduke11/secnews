"""v1 Case API — 共享序列化 helper (R3 拆自 case_api.py).

``_case_to_dict`` 服务于 write / update / relation 三族 handler;
``_list_response`` 服务于列表端点。
"""

from __future__ import annotations

from typing import Any

from backend.version import APP_VERSION as API_VERSION


def _case_to_dict(case) -> dict[str, Any]:
    """Pydantic Case → JSON dict (datetime ISO)."""
    return case.model_dump(mode="json")


def _list_response(items: list, total: int | None = None) -> dict[str, Any]:
    return {
        "version": API_VERSION,
        "items": [_case_to_dict(c) for c in items],
        "total": total if total is not None else len(items),
    }
