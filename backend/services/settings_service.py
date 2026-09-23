"""Settings KV service — settings 表服务出口 (R3: api 层禁直连 repository)。

封装 :class:`SettingsRepository` 的 get/set/delete/list_all; ``set`` 成功后
写 ``audit_log`` (record_audit 全异常吞, 审计失败不阻塞业务)。P3 Task 14 将
在此叠加 ``_ALLOWED_PREFIXES`` namespace 契约 (未注册前缀 fail-loud)。
"""
from __future__ import annotations

from typing import Any

from backend.repository.settings_repo import SettingsRepository


class SettingsService:
    """settings KV 读写门面 — 写入即审计 (actor/action/detail 可定制)。"""

    def get(self, key: str, default: Any = None) -> Any:
        return SettingsRepository().get(key, default)

    def list_all(self) -> dict[str, Any]:
        return SettingsRepository().list_all()

    def set(
        self,
        key: str,
        value: Any,
        *,
        actor: str = "web",
        action: str = "settings.set",
        detail: dict[str, Any] | None = None,
    ) -> None:
        # 调用方未传 detail 时补 from/to 语义; 传了则尊重调用方 (省一次读)。
        old = self.get(key) if detail is None else None
        SettingsRepository().set(key, value)
        from backend.observability_records import record_audit

        record_audit(
            actor,
            action,
            target=key,
            detail=detail if detail is not None else {"from": old, "to": value},
        )

    def delete(self, key: str) -> bool:
        return SettingsRepository().delete(key)


__all__ = ["SettingsService"]
