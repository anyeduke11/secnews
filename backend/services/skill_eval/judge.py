"""skill_eval.judge — 跑出 SkillRunResult 与 EvalFixture 断言对比 (C5).

``judge(run_result, fixture)`` → ``JudgeResult`` (含 AssertionResult 列表)

设计:
- 路径解析: ``target`` 字符串按 ``.`` 拆分; 例 "result.top5" → obj["result"]["top5"]
- result / meta 都可访问: judge 知道 SkillRunResult.result 是 dict, meta 是 dict
  (``result.foo`` 访问 result dict; ``meta.foo`` 访问 meta dict)
- 断言失败写 AssertionResult(passed=False, reason=...) 不抛异常 (R8: 多条断言
  全跑完再汇总); 只在 ``fixture.assertions`` 为空 → JudgeResult 自身失败
- skip_if_null / skip_if_empty: 当目标值为 None / list 空 时该条断言 skip
  (passed=True + reason 含 "skipped"), 不计入 failed
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.services.skill_eval.dataset import Assertion, EvalFixture
from backend.services.skill_eval.runner import SkillRunResult

__all__ = ["AssertionResult", "JudgeResult", "judge"]


@dataclass(frozen=True)
class AssertionResult:
    """单条断言的执行记录; passed / reason 均为最终态."""

    assertion: Assertion
    passed: bool
    actual: Any = None
    reason: str = ""


@dataclass(frozen=True)
class JudgeResult:
    """单 fixture 总体判分; passed = 所有 assertion 通过 (含 skipped)."""

    fixture_id: str
    passed: bool
    assertions: list[AssertionResult] = field(default_factory=list)
    summary: str = ""

    @property
    def failed_count(self) -> int:
        return sum(1 for a in self.assertions if not a.passed)

    @property
    def passed_count(self) -> int:
        return sum(1 for a in self.assertions if a.passed)


# ---------------------------------------------------------------------------
# 路径解析
# ---------------------------------------------------------------------------
def _resolve(target: str, run: SkillRunResult) -> Any:
    """``target`` 字符串 → 值; 支持 ``result.x.y`` / ``meta.x.y`` / 顶层属性.

    优先级 (从窄到宽):
    1. ``result.*`` → run.result dict 路径
    2. ``meta.*``  → run.meta dict 路径
    3. 其他顶层   → run.result.get(top); 若仍 None, 回落 run 属性 (如
       ``duration_ms`` / ``error`` / ``fixture_id``)
    """
    if not target:
        raise ValueError("target 不能为空")
    parts = target.split(".")
    head, *rest = parts
    if head == "result":
        obj: Any = run.result
    elif head == "meta":
        obj = run.meta
    else:
        obj = run.result.get(head) if isinstance(run.result, dict) else None
        if obj is None and rest == []:
            # 顶层属性 (duration_ms / error / fixture_id / skill_id / playbook)
            obj = getattr(run, head, None)
    for p in rest:
        if isinstance(obj, dict):
            obj = obj.get(p)
        else:
            obj = getattr(obj, p, None)
        if obj is None:
            return None
    return obj


# ---------------------------------------------------------------------------
# 单条断言执行
# ---------------------------------------------------------------------------
def _type_name(value: Any) -> str:
    return type(value).__name__


def _eval_assertion(a: Assertion, run: SkillRunResult) -> AssertionResult:
    """执行单条断言; 失败写 reason, 不抛."""
    if a.type == "type_check":
        actual = _resolve(a.target, run)
        return AssertionResult(
            assertion=a,
            passed=_type_name(actual) == a.expected,
            actual=actual,
            reason="" if _type_name(actual) == a.expected else f"got {_type_name(actual)}, expected {a.expected}",
        )

    if a.type == "equal":
        actual = _resolve(a.target, run)
        return AssertionResult(
            assertion=a,
            passed=actual == a.expected,
            actual=actual,
            reason="" if actual == a.expected else f"got {actual!r}, expected {a.expected!r}",
        )

    if a.type == "range":
        actual = _resolve(a.target, run)
        if a.skip_if_null and actual is None:
            return AssertionResult(assertion=a, passed=True, actual=actual, reason="skipped (null)")
        if not isinstance(actual, (int, float)):
            return AssertionResult(
                assertion=a,
                passed=False,
                actual=actual,
                reason=f"value must be number, got {_type_name(actual)}",
            )
        lo = -float("inf") if a.min is None else a.min
        hi = float("inf") if a.max is None else a.max
        in_range = lo <= actual <= hi
        return AssertionResult(
            assertion=a,
            passed=in_range,
            actual=actual,
            reason="" if in_range else f"{actual} not in [{lo}, {hi}]",
        )

    if a.type == "field_type":
        actual = _resolve(a.target, run)
        return AssertionResult(
            assertion=a,
            passed=_type_name(actual) == a.expected,
            actual=actual,
            reason="" if _type_name(actual) == a.expected else f"got {_type_name(actual)}, expected {a.expected}",
        )

    if a.type == "length_eq":
        actual = _resolve(a.target, run)
        if actual is None:
            return AssertionResult(assertion=a, passed=False, actual=actual, reason="value is None")
        try:
            length = len(actual)
        except TypeError:
            return AssertionResult(assertion=a, passed=False, actual=actual, reason=f"value has no len(), got {_type_name(actual)}")
        return AssertionResult(
            assertion=a,
            passed=length == a.expected,
            actual=actual,
            reason="" if length == a.expected else f"len {length} != {a.expected}",
        )

    if a.type in (
        "list_field_type",
        "list_field_eq",
        "list_field_range",
        "list_field_min",
        "list_field_min_length",
    ):
        return _eval_list_field(a, run)

    if a.type == "list_avg_above":
        return _eval_list_avg_above(a, run)

    if a.type == "dict_has_keys":
        return _eval_dict_has_keys(a, run)

    return AssertionResult(
        assertion=a,
        passed=False,
        actual=None,
        reason=f"unsupported assertion.type {a.type!r}",
    )


def _eval_list_field(a: Assertion, run: SkillRunResult) -> AssertionResult:
    lst = _resolve(a.target, run)
    if a.skip_if_empty and (lst is None or len(lst) == 0):
        return AssertionResult(assertion=a, passed=True, actual=lst, reason="skipped (empty list)")
    if not isinstance(lst, list):
        return AssertionResult(assertion=a, passed=False, actual=lst, reason=f"target not a list, got {_type_name(lst)}")
    field = a.field
    if field is None:
        return AssertionResult(assertion=a, passed=False, actual=lst, reason="missing field (assertion.field)")
    bad: list[tuple[int, str]] = []
    for i, item in enumerate(lst):
        if not isinstance(item, dict):
            bad.append((i, f"item not dict, got {_type_name(item)}"))
            continue
        v = item.get(field)
        if a.type == "list_field_type":
            if _type_name(v) != a.expected:
                bad.append((i, f"got {_type_name(v)}, expected {a.expected}"))
        elif a.type == "list_field_eq":
            if v != a.expected:
                bad.append((i, f"got {v!r}, expected {a.expected!r}"))
        elif a.type == "list_field_range":
            lo = -float("inf") if a.min is None else a.min
            hi = float("inf") if a.max is None else a.max
            if not isinstance(v, (int, float)) or not (lo <= v <= hi):
                bad.append((i, f"{v} not in [{lo}, {hi}]"))
        elif a.type == "list_field_min":
            if not isinstance(v, (int, float)) or v < (a.min or 0):
                bad.append((i, f"{v} < {a.min}"))
        elif a.type == "list_field_min_length":
            if not isinstance(v, str) or len(v) < (a.min_length or 0):
                bad.append((i, f"len {len(v) if isinstance(v, str) else '?'} < {a.min_length}"))
    passed = not bad
    reason = "" if passed else f"{len(bad)}/{len(lst)} items failed (e.g. idx={bad[0][0]}: {bad[0][1]})"
    return AssertionResult(assertion=a, passed=passed, actual=lst, reason=reason)


def _eval_list_avg_above(a: Assertion, run: SkillRunResult) -> AssertionResult:
    lst = _resolve(a.target, run)
    if a.skip_if_empty and (lst is None or len(lst) == 0):
        return AssertionResult(assertion=a, passed=True, actual=lst, reason="skipped (empty list)")
    if not isinstance(lst, list) or not lst:
        return AssertionResult(assertion=a, passed=False, actual=lst, reason="list empty or not a list")
    field = a.field
    if field is None:
        return AssertionResult(assertion=a, passed=False, actual=lst, reason="missing field")
    vals: list[float] = []
    for it in lst:
        if isinstance(it, dict):
            v = it.get(field)
            if isinstance(v, (int, float)):
                vals.append(float(v))
    if not vals:
        return AssertionResult(assertion=a, passed=False, actual=lst, reason="no numeric items")
    avg = sum(vals) / len(vals)
    threshold = a.threshold if a.threshold is not None else 0.0
    return AssertionResult(
        assertion=a,
        passed=avg > threshold,
        actual=avg,
        reason="" if avg > threshold else f"avg {avg:.4f} not > {threshold}",
    )


def _eval_dict_has_keys(a: Assertion, run: SkillRunResult) -> AssertionResult:
    obj = _resolve(a.target, run)
    if not isinstance(obj, dict):
        return AssertionResult(assertion=a, passed=False, actual=obj, reason=f"target not dict, got {_type_name(obj)}")
    keys = a.expected
    if not isinstance(keys, list):
        return AssertionResult(assertion=a, passed=False, actual=obj, reason="expected must be list of keys")
    missing = [k for k in keys if k not in obj]
    return AssertionResult(
        assertion=a,
        passed=not missing,
        actual=obj,
        reason="" if not missing else f"missing keys: {missing}",
    )


# ---------------------------------------------------------------------------
# 顶层 judge
# ---------------------------------------------------------------------------
def judge(run: SkillRunResult, fixture: EvalFixture) -> JudgeResult:
    """单 fixture 一次性跑完所有断言, 汇总 JudgeResult."""
    if run.error is not None:
        # runner 阶段失败 → 整 fixture 算 fail, 全部断言记 skipped
        results = [
            AssertionResult(
                assertion=a,
                passed=False,
                actual=None,
                reason=f"runner error: {run.error}",
            )
            for a in fixture.assertions
        ]
        return JudgeResult(
            fixture_id=fixture.id,
            passed=False,
            assertions=results,
            summary=f"runner error: {run.error}",
        )

    results = [_eval_assertion(a, run) for a in fixture.assertions]
    failed = sum(1 for r in results if not r.passed)
    passed = failed == 0
    summary = (
        f"all {len(results)} assertions passed"
        if passed
        else f"{failed}/{len(results)} assertions failed"
    )
    return JudgeResult(
        fixture_id=fixture.id,
        passed=passed,
        assertions=results,
        summary=summary,
    )