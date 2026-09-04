"""trigger_gate.triggers — 触发源适配层 (v0.8 Phase D D1).

包内 3 个适配器, 各对应一个合法 source:
- :class:`webhook`        — HTTP webhook 适配 (R7 验证签名 + 限流)
- :class:`kl_event`       — KL T1-T5 完成事件 → "质量巡检" skill (联动验证)
- :class:`collector_event` — collector 失败/超时事件 → "信源健康扫描" skill

每个适配器暴露 ``submit(...)`` 函数, 内部统一调
``trigger_gate.submit(source=..., ...)`` 入队。

设计要点 (R7/R8):
- webhook 接受 (path, payload, signature?) 三元组; 签名缺失或错误抛
  SignatureInvalidError (R7, fail loud)
- kl_event 接受 (stage, item_id) 元组; stage ∈ T1..T5 + 已完成
- collector_event 接受 (collector_name, status, error?) 元组; status ∈
  success / failed / timeout
"""
from __future__ import annotations

from backend.services.trigger_gate.triggers.collector_event import (
    CollectorEventTrigger,
    InvalidCollectorStatusError,
)
from backend.services.trigger_gate.triggers.kl_event import (
    InvalidKLEventError,
    KLEventTrigger,
)
from backend.services.trigger_gate.triggers.webhook import (
    SignatureInvalidError,
    WebhookTrigger,
)

__all__ = [
    "CollectorEventTrigger",
    "InvalidCollectorStatusError",
    "InvalidKLEventError",
    "KLEventTrigger",
    "SignatureInvalidError",
    "WebhookTrigger",
]