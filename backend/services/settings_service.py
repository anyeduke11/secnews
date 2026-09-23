"""Settings KV service — settings 表服务出口 (R3: api 层禁直连 repository)。

封装 :class:`SettingsRepository` 的 get/set/delete/list_all; ``set`` 成功后
写 ``audit_log`` (record_audit 全异常吞, 审计失败不阻塞业务)。

P3 Task 14 (2026-09-22 设置重构, 设计稿 §5): ``set`` 叠加 namespace 契约 —
写入必须落在 ``_ALLOWED_PREFIXES`` 注册前缀内, 未注册前缀 fail-loud
(InvalidParamException), 防止 settings 表继续被任意 namespace 侵蚀。
"""
from __future__ import annotations

from typing import Any

from backend.exceptions import InvalidParamException
from backend.repository.settings_repo import SettingsRepository

# settings 表 namespace 契约 (2026-09-22 P3, 设计稿 §5): 写入必须落在已注册前缀内。
# state.* = 运行状态例外清单 (mitre 同步位点/dsh 模式等既有 key, 只读迁移不硬改)。
# secrets.oauth_allowlist / webhook.secret = 精确键混入 (前者 OAuth 白名单既有存储位;
# 后者 vault 迁移完成前过渡放行, Task 15 落地后移入 _DISALLOWED_EXACT)。
_ALLOWED_PREFIXES = (
    "collection.", "llm.", "interest.", "quality.", "feature.",
    "feature-gates.", "state.", "secrets.oauth_allowlist", "webhook.secret",
)
# Task 15 迁移 webhook.secret 后填 {"webhook.secret"} — 明文回写通道永久关闭。
_DISALLOWED_EXACT: set[str] = set()


class SettingsService:
    """settings KV 读写门面 — 写入即审计 + namespace 契约 (P3)。"""

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
        target: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        # namespace 契约 fail-loud (设计稿 §5): 拒绝发生在 repo.set/audit 之前。
        if key in _DISALLOWED_EXACT or not key.startswith(_ALLOWED_PREFIXES):
            raise InvalidParamException(
                f"settings key '{key}' 不在注册前缀内; "
                f"新 key 须先在本契约登记 (设计稿 §5)"
            )
        # 调用方未传 detail 时补 from/to 语义; 传了则尊重调用方 (省一次读)。
        old = self.get(key) if detail is None else None
        SettingsRepository().set(key, value)
        from backend.observability_records import record_audit

        record_audit(
            actor=actor,
            action=action,
            target=target if target is not None else key,
            detail=detail if detail is not None else {"from": old, "to": value},
        )

    def delete(self, key: str) -> bool:
        return SettingsRepository().delete(key)


__all__ = ["SettingsService"]
