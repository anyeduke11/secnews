"""Run 编排桥 — Action.start → Run 创建的单一桥接点 (Batch 4 解环).

背景: ``ActionService.start`` 需要调 ``RunService.create_or_replay`` 完成
action→run 启动桥接, 而 ``RunService.__init__`` 曾反向惰性 import
``ActionService`` (该引用自 C07 R05 移除 mock 协议后已无任何读取方, 属死代码),
形成 services 域唯一的模块级硬环:

    action_service ⇄ run_service   (环, 已解除)

解环后的 import 方向 (单向无环):

    action_service → run_orchestrator → run_service

本模块只承载桥接编排接口, **不改任何业务语义**:

- attempt 恒为 1; inputs 恒为 ``{"action_id", "plan_hash"}``;
- run 永远 queued 的生命周期语义、§7.4 三层幂等、异常类型
  (RunValidationError / RunConflictError) 与返回形状
  (``{"run": ..., "replayed": bool}``) 全部保留在 ``RunService`` 原样透传;
- run_service 注入优先 (ActionService._run_service), 缺省构造
  ``RunService()`` — 与原 ``start()`` 内 ``self._run_service or RunService()``
  语义等价。

P1-0 真实执行体 (run 派发/claim/finish 编排) 产品决策未做, 本模块暂只承载
启动桥接; 后续执行编排应落在本模块而非回填到 action/run 两服务, 以维持
单向 import 图 (R4 守卫: backend/tests/test_service_cycle_guard.py)。
"""
from __future__ import annotations

from typing import Any

from backend.services.run_service import RunService

__all__ = ["create_run_for_action_start"]


def create_run_for_action_start(
    *,
    action_id: str,
    plan_hash: str,
    idempotency_key: str,
    protocol: str,
    trigger_source: str = "user",
    skill_id: str | None = None,
    run_service: Any | None = None,
) -> dict[str, Any]:
    """action.start 桥接: 创建 (或三层幂等重放) Run。

    Args:
        action_id: 所属 action id。
        plan_hash: action 的 plan_hash (写入 run.inputs, 供 §7.4 body 比对)。
        idempotency_key: 幂等键 (原样透传 RunService.create_or_replay)。
        protocol: run 协议 (dsh / pi / direct)。
        trigger_source: 触发来源 (user / agent / system / scheduled / webhook)。
        skill_id: 关联 skill id (可空)。
        run_service: 注入的 RunService (单测/编排方覆写); None 时构造默认实例。

    Returns:
        RunService.create_or_replay 的原形状: ``{"run": <dict>, "replayed": bool}``。
        异常类型与三层幂等判定完全由 RunService 决定, 本函数不捕获不改写。
    """
    svc = run_service if run_service is not None else RunService()  # noqa: E711 — 有意用 is not None 而非真值判断, 允许测试注入 falsy mock
    return svc.create_or_replay(
        action_id=action_id, idempotency_key=idempotency_key, attempt=1,
        protocol=protocol, trigger_source=trigger_source, skill_id=skill_id,
        inputs={"action_id": action_id, "plan_hash": plan_hash},
    )
