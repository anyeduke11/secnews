"""playbook_engine.core — Playbook 数据类 + PlaybookEngine 主类 (C1).

公开 API:
- :class:`Playbook`         — 已加载的 playbook (含 metadata / inputs / steps / outputs)
- :class:`PlaybookStep`     — 单步声明 (id / kind / 字段为 kind 决定)
- :class:`StepKind`        — ``skill`` / ``api`` / ``condition`` 三选一 (R7 砍 script)
- :class:`StepResult`       — 单步执行结果 (status / output / error / elapsed_ms)
- :class:`PlaybookRun`      — 一次 execute 的完整轨迹 (steps_results + 终态)
- :class:`ValidationReport` — 校验报告 (errors + warnings)
- :class:`ValidationReportEntry` — 单条校验项
- :class:`PlaybookEngine`   — load / validate / execute 入口
- :func:`PlaybookEngine.execute` — 同步执行, 50step/1h 上限 + 危险命令拦截

边界 (V0.8_REFACTOR_PLAN.md §5):
- 50step / 1h → 强制停止 + partial 终态 (R6)
- script step → 抛 ValidationReport (RCE, R7)
- 危险命令黑名单 (P4-7 沿用) → execute 前 inspect, 命中即 422-like 抛错
- 引用未注册 skill (R8) → validate 报 error, execute 前拒绝

非目标 (C1 不做):
- 异步/并发 step — 按 spec 步骤顺序执行 (依赖链简单), 并发留 v0.9
- 状态持久化 — C1 在内存完成 PlaybookRun, 持久化留 C2 (cron 调 execute) + D1
  (webhook 触发) 时随 trigger_tickets + skill_runs 间接持久化
- DAG 调度 — 当前线性 step 顺序, DAG 留 v0.9
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from backend.logging_config import logger
from backend.services.playbook_engine.loader import (
    extract_inputs,
    extract_metadata,
    extract_steps,
    extract_trigger,
    load_playbook as _load_playbook_from_path,
)
from backend.services.playbook_engine.step import StepExecutor

# 公开常量: 50 step / 1h 上限 (R6)
MAX_STEPS: int = 50
MAX_TOTAL_SECONDS: int = 3600  # 1h

#: step 类型枚举 — R7 砍 script (RCE 边界)
StepKind = Literal["skill", "api", "condition"]


# ---------------------------------------------------------------------------
# P4-7 危险命令黑名单 — 沿用 codegarden_orchestration_service, C1 升级一并
# 统一到 PlaybookEngine (旧路径仍跑此检查以保留 P4-7 合规边界)
# ---------------------------------------------------------------------------
_DANGEROUS_PATTERNS: tuple[str, ...] = (
    r"\bsudo\b",
    r"\brm\s+-rf?\b",
    r"\bchmod\s+777\b",
    r"curl[^\n|]*\|\s*(ba)?sh\b",
    r"wget[^\n|]*\|\s*(ba)?sh\b",
    r"\beval\b",
    r"base64\s+-d",
    r"python\s+-c",
    r"bash\s+-c",
    r"/dev/null\s*;",
    r">\s*/etc/",
)


def _has_dangerous(text: str) -> str | None:
    """返回首个命中的危险模式, 否则 None."""
    lowered = text.lower()
    for pat in _DANGEROUS_PATTERNS:
        if re.search(pat, lowered):
            return pat
    return None


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------
@dataclass
class PlaybookStep:
    """单步声明 (YAML 解构结果)。

    字段语义随 kind 变化:
      - kind == "skill":     skill (str, 已注册 skill_id), params (dict)
      - kind == "api":       action (str, "METHOD /path"), body (dict | None)
      - kind == "condition": expr (str, 简单布尔表达式, 求值为 False 时跳过)
    """

    id: str
    kind: StepKind
    # common
    if_expr: str | None = None  # 顶层 if (expression, falsy 跳过整步); condition.kind 用 expr
    output: str | None = None  # 把本步结果命名到 step_output 上下文, 供后续 {{ steps.<output>.x }} 引用
    # skill
    skill: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    # api
    action: str | None = None
    body: dict[str, Any] | None = None
    # condition
    expr: str | None = None


@dataclass(frozen=True)
class Playbook:
    """已加载的 Playbook (YAML 解析 + 校验后产物)。

    fields:
        name:        playbook id (取自 metadata.name)
        desc:        描述 (metadata.desc)
        trigger:     触发声明 (cron spec / timezone); C2 scheduler 消费
        inputs:      用户可覆盖默认的输入 schema {key: {"type": str, "default": any}}
        steps:       步骤列表 (顺序即执行顺序)
        raw_path:    YAML 文件路径 (audit / 调试用)
        primary_output: 主输出 step_id (供 quick view)
    """

    name: str
    desc: str = ""
    owner: str = "user"
    tags: list[str] = field(default_factory=list)
    trigger: dict[str, Any] = field(default_factory=dict)
    inputs: dict[str, Any] = field(default_factory=dict)
    steps: list[PlaybookStep] = field(default_factory=list)
    raw_path: str = ""
    primary_output: str | None = None

    def to_summary(self) -> dict[str, Any]:
        """轻量 summary, 列表 API 用 (避免长 steps 噪声)。"""
        return {
            "name": self.name,
            "desc": self.desc,
            "owner": self.owner,
            "tags": list(self.tags),
            "trigger": dict(self.trigger),
            "step_count": len(self.steps),
            "primary_output": self.primary_output,
            "raw_path": self.raw_path,
        }


@dataclass
class ValidationReportEntry:
    """单条校验项 — errors 阻止 execute, warnings 仅日志。"""

    severity: Literal["error", "warning"]
    code: str
    message: str
    step_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"severity": self.severity, "code": self.code, "message": self.message}
        if self.step_id is not None:
            out["step_id"] = self.step_id
        return out


@dataclass
class ValidationReport:
    """校验报告 — errors 非空 = 拒绝执行 (fail loud)。"""

    entries: list[ValidationReportEntry] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationReportEntry]:
        return [e for e in self.entries if e.severity == "error"]

    @property
    def warnings(self) -> list[ValidationReportEntry]:
        return [e for e in self.entries if e.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [e.to_dict() for e in self.warnings],
        }


@dataclass
class StepResult:
    """单步执行结果 — 写入 PlaybookRun.steps。"""

    step_id: str
    kind: StepKind
    status: Literal["succeeded", "skipped", "failed"]
    output: Any = None
    error: str | None = None
    elapsed_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "kind": self.kind,
            "status": self.status,
            "output": self.output,
            "error": self.error,
            "elapsed_ms": self.elapsed_ms,
        }


@dataclass
class PlaybookRun:
    """一次 execute 的完整轨迹 (R3-style: 全 run 落 skill_runs)。

    fields:
        name:       playbook 名 (沿用)
        run_id:     ulid-like uuid4 hex (短前缀, 与 trigger-gate 风格一致)
        status:     'succeeded' / 'partial' / 'failed' / 'stopped' (50step/1h 触发)
        inputs:     execute 入口传入的覆盖值
        steps:      各步骤结果 (顺序与 playbook.steps 一致)
        started_at: ISO UTC
        finished_at: ISO UTC
        error:      终态错误 (partial/failed)
    """

    name: str
    run_id: str
    status: str = "running"
    inputs: dict[str, Any] = field(default_factory=dict)
    steps: list[StepResult] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "run_id": self.run_id,
            "status": self.status,
            "inputs": dict(self.inputs),
            "steps": [s.to_dict() for s in self.steps],
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# PlaybookEngine — 主类
# ---------------------------------------------------------------------------
class PlaybookEngine:
    """Playbook YAML 加载/校验/执行。

    构造参数:
        skill_registry:   SkillRegistry 实例; 用于 R8 校验 skill 引用是否已注册
                          (缺省走 builtin.BUILTIN 单例, 测试可注入 fake)
        step_executor_cls: StepExecutor 工厂 (测试可注入 fake executor)
        max_steps:        步骤上限 (默认 50, R6)
        max_total_seconds: 总时长上限秒 (默认 3600, R6)
    """

    def __init__(
        self,
        skill_registry: Any | None = None,
        step_executor_cls: type[StepExecutor] | None = None,
        *,
        max_steps: int = MAX_STEPS,
        max_total_seconds: int = MAX_TOTAL_SECONDS,
    ) -> None:
        if skill_registry is None:
            # 惰性 import 避免循环 (skill_registry 也避免反向依赖 playbook)
            from backend.services.skill_registry.builtin import BUILTIN

            skill_registry = BUILTIN
        self._registry = skill_registry
        self._executor_cls = step_executor_cls or StepExecutor
        self.max_steps = max_steps
        self.max_total_seconds = max_total_seconds

    # ------------------------------------------------------------------
    # load
    # ------------------------------------------------------------------
    def load(self, path: str) -> Playbook:
        """从 YAML 文件加载并解析为 Playbook (不校验, 调用 validate 才返回 report)。

        路径不存在 / YAML 语法错 → 抛 ValueError; 解析结构错 (顶层非 dict /
        kind 缺失 / metadata.name 缺失) → 抛 ValueError。
        """
        return _load_playbook_from_path(path)

    # ------------------------------------------------------------------
    # validate
    # ------------------------------------------------------------------
    def validate(self, pb: Playbook) -> ValidationReport:
        """按 R6/R7/R8 + P4-7 规则逐项校验。

        errors 非空 → execute 拒绝; warnings → 仅日志。
        """
        report = ValidationReport()

        # R6: 50 step 上限
        if len(pb.steps) > self.max_steps:
            report.entries.append(
                ValidationReportEntry(
                    severity="error",
                    code="STEP_LIMIT_EXCEEDED",
                    message=f"playbook 含 {len(pb.steps)} 步, 超出 {self.max_steps} 上限 (R6)",
                )
            )

        seen_ids: set[str] = set()
        for step in pb.steps:
            # step.id 重复
            if step.id in seen_ids:
                report.entries.append(
                    ValidationReportEntry(
                        severity="error",
                        code="DUPLICATE_STEP_ID",
                        message=f"step id {step.id!r} 重复",
                        step_id=step.id,
                    )
                )
            seen_ids.add(step.id)

            # kind 合法性 (R7 砍 script)
            if step.kind not in ("skill", "api", "condition"):
                report.entries.append(
                    ValidationReportEntry(
                        severity="error",
                        code="DISALLOWED_STEP_KIND",
                        message=(
                            f"step kind {step.kind!r} 禁止 — R7 仅允许 "
                            f"skill / api / condition; script step = RCE 边界"
                        ),
                        step_id=step.id,
                    )
                )

            # skill 引用注册 (R8)
            if step.kind == "skill":
                if not step.skill:
                    report.entries.append(
                        ValidationReportEntry(
                            severity="error",
                            code="MISSING_SKILL_REF",
                            message="skill 步骤未指定 skill id",
                            step_id=step.id,
                        )
                    )
                else:
                    try:
                        self._registry.get(step.skill)
                    except Exception:
                        report.entries.append(
                            ValidationReportEntry(
                                severity="error",
                                code="UNREGISTERED_SKILL_REF",
                                message=f"skill {step.skill!r} 未注册 (R8 悬空引用)",
                                step_id=step.id,
                            )
                        )

            # api 步骤: action 必须 "METHOD /path" 且 path 在白名单
            if step.kind == "api":
                if not step.action or " " not in step.action:
                    report.entries.append(
                        ValidationReportEntry(
                            severity="error",
                            code="INVALID_API_ACTION",
                            message="api 步骤 action 必须形如 'METHOD /path'",
                            step_id=step.id,
                        )
                    )
                else:
                    _, path = step.action.split(" ", 1)
                    # 默认白名单与 StepExecutor.api_whitelist 同步 (本机 /api/*)
                    whitelist = ("/api/",)
                    if not any(path.startswith(p) for p in whitelist):
                        report.entries.append(
                            ValidationReportEntry(
                                severity="error",
                                code="API_PATH_NOT_WHITELISTED",
                                message=f"api path {path!r} 不在白名单 {whitelist} (C1 RCE 边界)",
                                step_id=step.id,
                            )
                        )

            # 危险命令黑名单 (P4-7 沿用, 即使 api step 也扫 body 字符串)
            haystack = " ".join(
                str(v)
                for v in (
                    step.params.values() if step.params else (),
                    step.body.values() if step.body else (),
                    (step.action or "",),
                    (step.expr or "",),
                )
                if v is not None
            )
            hit = _has_dangerous(haystack)
            if hit:
                report.entries.append(
                    ValidationReportEntry(
                        severity="error",
                        code="DANGEROUS_PATTERN",
                        message=f"step 含危险模式 {repr(hit)}, 已拦截 (P4-7)",
                        step_id=step.id,
                    )
                )

            # primary_output 引用存在
            if pb.primary_output and pb.primary_output not in seen_ids and step.id == pb.steps[-1].id:
                report.entries.append(
                    ValidationReportEntry(
                        severity="warning",
                        code="PRIMARY_OUTPUT_NOT_REACHED",
                        message=f"primary_output {pb.primary_output!r} 不在 step id 集合中",
                    )
                )

        return report

    # ------------------------------------------------------------------
    # execute
    # ------------------------------------------------------------------
    def execute(
        self,
        pb: Playbook,
        inputs: dict[str, Any] | None = None,
    ) -> PlaybookRun:
        """同步执行 playbook; 终态 (succeeded / partial / failed / stopped) 必落。

        Raises:
            ValueError: validate 失败 (errors 非空) 时抛错, 阻止执行
        """
        report = self.validate(pb)
        if not report.ok:
            codes = ", ".join(e.code for e in report.errors)
            raise ValueError(f"playbook validate failed: {codes} — {report.to_dict()}")

        merged_inputs = self._resolve_inputs(pb, inputs or {})
        import uuid

        run = PlaybookRun(
            name=pb.name,
            run_id=f"pb-{uuid.uuid4().hex[:12]}",
            inputs=merged_inputs,
        )

        executor = self._executor_cls(registry=self._registry, run=run, playbook=pb)
        deadline = time.monotonic() + self.max_total_seconds
        any_failure = False
        primary_output: Any = None

        for idx, step in enumerate(pb.steps):
            # R6: 1h 上限检查
            if time.monotonic() > deadline:
                run.steps.append(
                    StepResult(
                        step_id=step.id,
                        kind=step.kind,
                        status="skipped",
                        error=f"playbook 超出 {self.max_total_seconds}s 上限 (R6)",
                    )
                )
                run.status = "stopped"
                run.error = "total_seconds_exceeded"
                break

            # 顶层 if (condition.kind 使用 expr, 其他 kind 也支持 if)
            if step.if_expr and not executor.eval_expr(step.if_expr):
                run.steps.append(
                    StepResult(step_id=step.id, kind=step.kind, status="skipped")
                )
                continue

            t0 = time.monotonic()
            try:
                output = executor.execute_step(step)
                elapsed = int((time.monotonic() - t0) * 1000)
                run.steps.append(
                    StepResult(
                        step_id=step.id,
                        kind=step.kind,
                        status="succeeded",
                        output=output,
                        elapsed_ms=elapsed,
                    )
                )
                if step.output:
                    executor.set_step_output(step.output, output)
                if pb.primary_output == step.id:
                    primary_output = output
            except Exception as e:  # noqa: BLE001 — playbook step 边界, 上层收口
                elapsed = int((time.monotonic() - t0) * 1000)
                run.steps.append(
                    StepResult(
                        step_id=step.id,
                        kind=step.kind,
                        status="failed",
                        error=str(e),
                        elapsed_ms=elapsed,
                    )
                )
                any_failure = True
                logger.warning(
                    "playbook_engine execute step failed",
                    extra={"trace_id": "", "playbook": pb.name, "step_id": step.id, "error": str(e)},
                )
                # 后续步默认跳过 (除非步骤自带 on_failure=continue; C1 不实现)
                break

        run.finished_at = datetime.now(timezone.utc).isoformat()
        if run.status == "running":
            run.status = "partial" if any_failure else "succeeded"
        # 把 primary_output 贴回终态
        if primary_output is not None and run.status == "succeeded":
            run.inputs["_primary_output"] = primary_output
        return run

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _resolve_inputs(self, pb: Playbook, overrides: dict[str, Any]) -> dict[str, Any]:
        """inputs 合并: schema 默认 + 用户覆盖 (后者胜)."""
        merged: dict[str, Any] = {}
        for key, spec in (pb.inputs or {}).items():
            if isinstance(spec, dict) and "default" in spec:
                merged[key] = spec["default"]
            else:
                merged[key] = None
        merged.update(overrides or {})
        return merged


__all__ = [
    "MAX_STEPS",
    "MAX_TOTAL_SECONDS",
    "Playbook",
    "PlaybookEngine",
    "PlaybookRun",
    "PlaybookStep",
    "StepKind",
    "StepResult",
    "ValidationReport",
    "ValidationReportEntry",
]