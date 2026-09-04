"""skill_eval.runner — 跑一个 fixture, 产出 SkillRunResult (C5).

设计:
- ``run_fixture(fixture, engine)`` 调用 engine 跑 skill / playbook
- engine 是抽象协议 (本文件用 ``SkillEvalEngine`` Protocol, 不引入 ABC);
  仓库真实 engine 在 B2/B3 落地, C5 测试用 FakeEngine (deterministic dict)
- ``SkillRunResult`` 承载 result 字典 + meta 元信息 (call_count / duration_ms)
  + error 字段 (None 表示未抛异常; judge 据此判 success)

call_count 与 duration_ms 用途:
- call_count == 1 (B 类直查) — judge 据此校验 B 类不编排
- duration_ms < 30000 — judge 据此判执行预算合规
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from backend.services.skill_eval.dataset import EvalFixture

__all__ = ["FixtureRunner", "SkillEvalEngine", "SkillRunResult", "run_fixture"]


@dataclass
class SkillRunResult:
    """单 fixture 跑出的结果 + 元信息."""

    fixture_id: str
    skill_id: str | None
    playbook: str | None
    result: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0

    @property
    def success(self) -> bool:
        return self.error is None


class SkillEvalEngine(Protocol):
    """评测用 engine 协议 — 真实 engine 在 B2/B3 接线, C5 仅 Protocol 占位.

    ``run_skill(skill_id, inputs)`` → dict (skill 返回值 + 框架包装字段)
    ``run_playbook(playbook_name, inputs)`` → dict (steps + outputs)
    """

    def run_skill(self, skill_id: str, inputs: dict[str, Any]) -> dict[str, Any]: ...

    def run_playbook(self, playbook_name: str, inputs: dict[str, Any]) -> dict[str, Any]: ...


class FixtureRunner:
    """承载 fixture → SkillRunResult; 提供单例化的 engine 注入."""

    def __init__(self, engine: SkillEvalEngine) -> None:
        self._engine = engine

    def run(self, fixture: EvalFixture) -> SkillRunResult:
        """跑一个 fixture; 失败 → SkillRunResult.error 填字符串 (不抛异常)."""
        started = time.monotonic()
        meta: dict[str, Any] = {"call_count": 0}
        result: dict[str, Any] = {}
        err: str | None = None
        try:
            if fixture.kind == "skill":
                assert fixture.skill_id is not None
                result = self._engine.run_skill(fixture.skill_id, fixture.inputs)
                meta["call_count"] = 1
            elif fixture.kind == "playbook":
                assert fixture.playbook is not None
                result = self._engine.run_playbook(fixture.playbook, fixture.inputs)
                meta["call_count"] = max(
                    len(result.get("steps", []) or []), 1
                )
            else:
                err = f"fixture kind {fixture.kind!r} 不支持"
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        duration_ms = int((time.monotonic() - started) * 1000)
        return SkillRunResult(
            fixture_id=fixture.id,
            skill_id=fixture.skill_id,
            playbook=fixture.playbook,
            result=result,
            meta=meta,
            error=err,
            duration_ms=duration_ms,
        )


def run_fixture(fixture: EvalFixture, engine: SkillEvalEngine) -> SkillRunResult:
    """便捷函数; 与 FixtureRunner().run(...) 等价."""
    return FixtureRunner(engine).run(fixture)