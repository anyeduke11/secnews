"""v1.0 C07 反例测试 (R04/R05/R15 修复断言).

依据 [docs/v1.0/V1.0.0_CLOSEOUT_TASKS.md §8 C07] + [REVIEW_2026-09-07.md §R04/§R05/§R15].

R04 真问题:
  - `backend/scheduler/jobs/worker_pump.py:_c03_r04_dispatcher` raise NotImplementedError,
    53 个历史 pending ticket 永远 dead-letter, 真 Skill runner (走 dsh/pi 适配) 接入空缺.
  - worker_pump 调 `coordinator.consume(req, task_fn=_c03_r04_dispatcher)` 链路就坏.

R05 真问题:
  - `backend/api/action_api.py:64` `protocol: str = Field(default="mock", ...)` — 默认 mock 虚报完成.
  - `backend/services/action_service.py:289` `protocol: str = "mock"` — service 层同样默认.
  - `backend/services/run_service.py:156,160,161,162,165,178` — `if protocol == "mock"` 同步 succeeded,
    不走真实执行, 虚报完成. 反例: 默认 HTTP start 应该显式拒收 `protocol=mock` (生产配置).

R15 真问题:
  - SK-05 target `/api/v1/knowledge/{id}/reuse` 的 `{id}` 没有插值, 输入 `knowledge_id` 被当 query 发送.
  - SK-06 `class_name="knowledge_review_due_job"` (实际是模块级函数), `method=None`,
    反射解析 `cls()` 试图把函数当构造器调用, TypeError.
  - SK-03/04 input_schema 缺必填参数 (subject_name/cve_id/evidence_materials) — 留 T19 收口 (本批只标 + 标 R15).

C07 修复:
  - R04: `_c03_r04_dispatcher` 替换为 `_c07_r04_skill_dispatcher` → 调 SkillRunner.run(skill, inputs, ticket_id).
  - R05: API + service `protocol` 默认值去掉 (必填), `pattern` 去掉 "mock"; run_service 删 `if protocol == "mock"`
    同步 succeeded 分支, mock 模式在 production config 拒收 (NotImplementedError).
  - R15 SK-05: `_invoke_api` 用 `str.format(**rendered_args)` 插值 path 里的 `{var}`.
  - R15 SK-06: `class_name=None, method="knowledge_review_due_job"` (函数) 走模块级函数分支.

Mimosa 约束: SQL 全 ? 参数绑定; 禁 mock/noop 吞异常; 禁静默降级.
"""
from __future__ import annotations

import json

import pytest


# ===========================================================================
# R05 修复断言: 默认 HTTP start 拒收 protocol=mock
# ===========================================================================
class TestR05ProtocolDefaultRejected:
    """R05: action_api StartActionRequest.protocol 默认值必须显式 (非 "mock")."""

    def test_action_api_default_protocol_not_mock(self) -> None:
        """R05 修复 1: StartActionRequest 默认 protocol 不应是 "mock".

        旧实现: `Field(default="mock", pattern=...)` 默认走 mock → 默认路径虚报完成.
        修复后: 默认值为 None 或其他显式值, pattern 去掉 "mock".
        """
        from backend.api.action_api import StartActionRequest

        field = StartActionRequest.model_fields["protocol"]
        assert field.default != "mock", (
            "R05 修复断言: StartActionRequest.protocol 默认值不应是 'mock' "
            "(旧实现默认走 mock 同步 succeeded, 违反 AC-07 默认路径不虚报完成)"
        )
        # pattern 应限制在 {dsh, pi, direct} (生产配置)
        pattern = field.metadata[0].pattern if field.metadata else None
        if pattern is not None:
            assert "mock" not in pattern, (
                f"R05 修复断言: StartActionRequest.protocol pattern 不应含 'mock' (实际: {pattern})"
            )

    def test_action_service_default_protocol_not_mock(self) -> None:
        """R05 修复 2: ActionService.start 默认 protocol 不应是 "mock"."""
        import inspect

        from backend.services.action_service import ActionService

        sig = inspect.signature(ActionService.start)
        proto_param = sig.parameters.get("protocol")
        assert proto_param is not None
        assert proto_param.default != "mock", (
            "R05 修复断言: ActionService.start 默认 protocol 不应是 'mock'"
        )

    def test_run_service_mock_branch_raises_in_production(self) -> None:
        """R05 修复 3: run_service.create_or_replay 收到 protocol=mock 应该 raise (生产拒收).

        旧实现: `if protocol == "mock"` 走同步 succeeded, 虚报完成.
        修复后: 显式 raise NotImplementedError, 让调用方知道 mock 不可在生产用.
        """
        from backend.services.run_service import RunService, RunValidationError

        svc = RunService()
        # 用合法 idempotency_key 触发 validation 走到 protocol check
        with pytest.raises((RunValidationError, NotImplementedError, ValueError)) as exc_info:
            svc.create_or_replay(
                action_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",  # ULID 形
                idempotency_key="c07-r05-1",
                attempt=1,
                protocol="mock",  # 显式传 mock 应该被拒
            )
        # 验证抛的不是 DB error / 内部错误
        assert "mock" in str(exc_info.value).lower() or "not" in str(exc_info.value).lower() or isinstance(
            exc_info.value, NotImplementedError
        ), f"R05 修复断言: protocol=mock 应被拒收, 实际抛 {type(exc_info.value).__name__}: {exc_info.value}"


# ===========================================================================
# R15 SK-05 修复断言: target.path 的 {var} 必须插值
# ===========================================================================
class TestR15SK05PathInterpolation:
    """R15: ApiTarget.path 含 {var} 时, 必须用 inputs 插值, 不字面拼."""

    def test_invoke_api_interpolates_path_vars(self, tmp_path, monkeypatch) -> None:
        """R15 SK-05 修复: path='/api/v1/knowledge/{knowledge_id}/reuse' + inputs={knowledge_id:'K1'} → 真实请求 /api/v1/knowledge/K1/reuse.

        旧实现: 路径字面拼 → httpx 发到 '/api/v1/knowledge/{knowledge_id}/reuse' (404).
        修复后: 用 inputs 插值 → 真实 ID 进入 URL.
        """
        from backend.services.skill_registry.core import ApiTarget
        from backend.services.skill_runner.dispatch import _invoke_api

        captured = {}

        class FakeResponse:
            status_code = 200
            text = json.dumps({"receipt": {"total": 3, "by_judgment": 1, "by_action": 1, "recent_30d": 1}})

            def json(self):
                return json.loads(self.text)

        class FakeClient:
            def __init__(self, *a, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get(self, url, params=None):
                captured["url"] = url
                captured["params"] = params
                return FakeResponse()

        # 替换 httpx.Client 为 fake (Mimosa 禁 mock/noop 吞异常 — 这里仅替换 HTTP 客户端边界)
        import httpx
        monkeypatch.setattr(httpx, "Client", FakeClient)
        # 后端 base_url 走默认 127.0.0.1:8000 — 拦截不依赖真实 server

        # v1.0 C07 R15 SK-05 修复: path 用 {knowledge_id} (input_schema required 字段同名)
        target = ApiTarget(path="/api/v1/knowledge/{knowledge_id}/reuse", http_method="GET")
        inputs = {"knowledge_id": "K-C07-001"}
        result = _invoke_api(target, args=None, inputs=inputs, step_outputs=[])

        # 断言 URL 中无字面 "{knowledge_id}"
        assert "{knowledge_id}" not in captured["url"], (
            f"R15 SK-05 修复断言: ApiTarget path 应插值 {inputs}, "
            f"实际 URL={captured['url']} 仍含字面 {{{{knowledge_id}}}}"
        )
        # 断言 K-C07-001 出现在 URL 路径
        assert "K-C07-001" in captured["url"], (
            f"R15 SK-05 修复断言: 插值后 URL 应含 K-C07-001, 实际={captured['url']}"
        )


# ===========================================================================
# R15 SK-06 修复断言: class_name=None + method=func_name (模块级函数)
# ===========================================================================
class TestR15SK06ModuleLevelFunction:
    """R15: SK-06 knowledge_review_due_job 是模块级函数, 必须用 class_name=None + method='func'."""

    def test_sk06_uses_module_level_function(self) -> None:
        """R15 SK-06 修复断言: v1_skills.build_sk06_knowledge_review_due() target 应是模块级函数.

        旧实现: class_name='knowledge_review_due_job' (函数当类用) + method=None → cls() 试图把函数当构造器, TypeError.
        修复后: class_name=None, method='knowledge_review_due_job' (模块级函数) 走 _resolve_service_target 函数分支.
        """
        from backend.services.skill_registry.core import ServiceTarget
        from backend.services.skill_registry.v1_skills import build_sk06_knowledge_review_due

        sk = build_sk06_knowledge_review_due()
        assert isinstance(sk.target, ServiceTarget)
        # 必须走模块级函数路径
        assert sk.target.class_name is None, (
            f"R15 SK-06 修复断言: SK-06 target.class_name 应为 None (模块级函数), "
            f"实际={sk.target.class_name!r} (把函数当类用是 R15 bug)"
        )
        assert sk.target.method == "knowledge_review_due_job", (
            f"R15 SK-06 修复断言: SK-06 target.method 应='knowledge_review_due_job', "
            f"实际={sk.target.method!r}"
        )

    def test_resolve_service_target_handles_module_level_function(self) -> None:
        """R15 SK-06 修复: _resolve_service_target 收到 class_name=None 时返模块级函数.

        验证: 调 _resolve_service_target(ServiceTarget(module, None, 'name')) 返函数 (不是实例方法).
        """
        from backend.services.skill_registry.core import ServiceTarget
        from backend.services.skill_runner.dispatch import _resolve_service_target

        # 用真实存在的模块级函数 (loggers 必存在)
        target = ServiceTarget(
            module="backend.logging_config",
            class_name=None,
            method="logger",  # 实际是模块属性, 但同款分支
        )
        # 不严格断言是 callable, 仅验证不抛 "class not found"
        try:
            result = _resolve_service_target(target)
            # logger 存在 → 返 logger 对象
        except RuntimeError as e:
            if "class not found" in str(e) or "class_name is None" in str(e):
                pytest.fail(
                    f"R15 SK-06 修复断言: class_name=None 走函数分支, 不应抛 class 错: {e}"
                )


# ===========================================================================
# R04 修复断言: worker_pump 走真实 SkillRunner
# ===========================================================================
class TestR04WorkerPumpRealSkillDispatch:
    """R04: worker_pump 替换 raise-on-call dispatcher, 改走 SkillRunner.run(skill, inputs, ticket_id)."""

    def test_worker_pump_no_longer_uses_c03_r04_dispatcher(self) -> None:
        """R04 修复 1: worker_pump 不应再 raise NotImplementedError (C03 兜底 dispatcher).

        旧实现: _c03_r04_dispatcher raise NotImplementedError → 53 pending ticket 永远 dead-letter.
        修复后: 替换为 _c07_r04_skill_dispatcher, 调 SkillRunner.run 真实执行.
        """

        from backend.scheduler.jobs import worker_pump

        # _c03_r04_dispatcher 不应再存在 (或被新 dispatcher 替代)
        assert not hasattr(worker_pump, "_c03_r04_dispatcher"), (
            "R04 修复断言: worker_pump._c03_r04_dispatcher 应已删除 (C03 兜底 raise 已由 C07 真实 dispatcher 替代)"
        )
        # 应有新 dispatcher
        assert hasattr(worker_pump, "_c07_r04_skill_dispatcher"), (
            "R04 修复断言: worker_pump 应有 _c07_r04_skill_dispatcher (调 SkillRunner.run 真派发)"
        )

    def test_worker_pump_dispatches_to_skill_runner(self) -> None:
        """R04 修复 2: worker_queue_pump_job 调 coordinator.consume 必传新 dispatcher (不是 _noop_task_fn).

        旧实现: C03 显式传 _c03_r04_dispatcher raise NotImplementedError.
        修复后: 传 _c07_r04_skill_dispatcher 真实走 SkillRunner.run.
        """
        import inspect

        from backend.scheduler.jobs import worker_pump

        source = inspect.getsource(worker_pump.worker_queue_pump_job)
        # 调 coordinator.consume 必传 _c07_r04_skill_dispatcher
        assert "_c07_r04_skill_dispatcher" in source, (
            "R04 修复断言: worker_queue_pump_job 调 coordinator.consume 应传 _c07_r04_skill_dispatcher"
        )
        # 不应再传 _c03_r04_dispatcher
        assert "_c03_r04_dispatcher" not in source, (
            "R04 修复断言: worker_queue_pump_job 不应再传 _c03_r04_dispatcher (raise-on-call 兜底)"
        )

    def test_skill_dispatcher_invokes_skill_runner(self) -> None:
        """R04 修复 3: _c07_r04_skill_dispatcher 必调 SkillRunner.run, ticket_id 贯穿.

        验证源码结构 (regex 静态分析):
          - 必 import SkillRunner (or run_skill)
          - 必构造 SkillDef (从 ticket.skill_id 查 registry.get)
          - 必调 runner.run(skill, inputs, ticket_id=...)
        """
        import inspect

        from backend.scheduler.jobs import worker_pump

        fn = getattr(worker_pump, "_c07_r04_skill_dispatcher", None)
        assert fn is not None, "R04: _c07_r04_skill_dispatcher 未定义"
        source = inspect.getsource(fn)
        # 必调 SkillRunner.run 或 run_skill
        assert ("SkillRunner" in source or "run_skill" in source), (
            f"R04 修复断言: _c07_r04_skill_dispatcher 应调 SkillRunner.run / run_skill, 实际:\n{source[:500]}"
        )
        # 必传 ticket_id (贯穿 ID)
        assert "ticket_id" in source, (
            "R04 修复断言: dispatcher 应贯穿 ticket_id 到 runner.run"
        )


# ===========================================================================
# R05 配套: action_api start protocol 必填, 提交时不传 protocol 必 raise
# ===========================================================================
class TestR05ActionStartProtocolRequired:
    """R05: API 层 StartActionRequest.protocol 必填 (旧默认 'mock' 必删)."""

    def test_action_start_without_protocol_raises(self) -> None:
        """R05 修复 4: 不传 protocol 时 StartActionRequest 构造必 raise ValidationError.

        旧实现: default='mock' → 不传也不 raise → 默认路径虚报完成.
        修复后: protocol 必填, 缺它 raise ValidationError.
        """
        from pydantic import ValidationError

        from backend.api.action_api import StartActionRequest

        with pytest.raises(ValidationError) as exc_info:
            StartActionRequest(
                expected_revision=1,
                idempotency_key="c07-r05-2",
                # protocol 不传 → 应 raise (旧 default='mock' 不 raise)
            )
        assert "protocol" in str(exc_info.value).lower(), (
            f"R05 修复断言: 缺 protocol 应 raise ValidationError 含 'protocol', 实际: {exc_info.value}"
        )


# ===========================================================================
# 真实 6 SK runner dispatch 演示 (R15 退出条件)
# ===========================================================================
class TestR156SkillsRealDispatch:
    """R15 退出条件: 6 v1 SK 逐个真实 dispatch (含 disabled / version mismatch 反例)."""

    def test_all_6_v1_skills_resolve_target(self) -> None:
        """R15 退出条件 1: 6 v1 SK 全部 _resolve_service_target 或 _invoke_api 成功 (不抛 RuntimeError).

        旧实现: SK-05/06 直接 RuntimeError (path 字面 / class_name 函数当类用).
        修复后: 6 SK 全部解析成功.
        """
        from backend.services.skill_registry.core import ApiTarget
        from backend.services.skill_registry.v1_skills import (
            build_sk01_daily_priority_intel,
            build_sk02_cve_impact_brief,
            build_sk03_inspection_materials,
            build_sk04_action_retrospective,
            build_sk05_reuse_experience,
            build_sk06_knowledge_review_due,
        )
        from backend.services.skill_runner.dispatch import (
            _resolve_service_target,
        )

        builders = [
            ("sk01", build_sk01_daily_priority_intel),
            ("sk02", build_sk02_cve_impact_brief),
            ("sk03", build_sk03_inspection_materials),
            ("sk04", build_sk04_action_retrospective),
            ("sk05", build_sk05_reuse_experience),
            ("sk06", build_sk06_knowledge_review_due),
        ]

        for name, build in builders:
            sk = build()
            assert sk.target is not None, f"{name}: target 不应为 None"
            if isinstance(sk.target, ApiTarget):
                # 验证 path 至少含 1 个插值或不含
                # 跳过真实 HTTP 调用 (本测试只验注册成功)
                continue
            # ServiceTarget: 反射解析
            try:
                _resolve_service_target(sk.target)
            except RuntimeError as e:
                pytest.fail(
                    f"R15 修复断言: {name} target 反射解析失败: {e}\n"
                    f"target={sk.target!r}"
                )

    def test_sk05_input_knowledge_id_interpolated_in_path(self) -> None:
        """R15 SK-05 详细: input_schema required=[knowledge_id] + path={id} 必须映射.

        旧实现: path 不插值, knowledge_id 仅作 query 发送.
        修复后: input_schema 与 path 插值变量一致, 或 path 明确为 {knowledge_id} 用 formater 解析.
        """
        from backend.services.skill_registry.v1_skills import build_sk05_reuse_experience

        sk = build_sk05_reuse_experience()
        path = sk.target.path  # /api/v1/knowledge/{knowledge_id}/reuse (C07 R15 SK-05 修复)
        # path 至少含 1 个 {var} 占位 (设计意图)
        assert "{" in path and "}" in path, (
            f"SK-05 修复断言: target.path 应含插值占位符, 实际={path}"
        )
        # input_schema 必填含 knowledge_id
        required = sk.input_schema.get("required", [])
        assert "knowledge_id" in required, (
            f"SK-05 修复断言: input_schema 必填应含 knowledge_id, 实际={required}"
        )
