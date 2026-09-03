"""skill_registry.loader — 启动加载校验 (feature_gate 锁, v0.8 Phase A · A2b).

职责: 在 register() 之前对整份 skill 清单做**纯结构校验**, 把契约违规
拦截在注册期而不是运行期。六条规则 (任务书 A2b §交付物 1):

①  id 全局唯一 — 重复 id 会让 get()/前端卡片路由歧义
②  feature_gate 非空且 == ``skill.<id>.enabled`` — 与 id 自洽, 防止
   gate 字符串拼错导致启停写到无人读取的 key
③  skill_type A/B/E 的 prompt_template 必须 None — 设计纪律 2
   (默认不调 LLM; 巡检/查询藏 LLM 摘要属无差别包装)
④  skill_type C/D 的 prompt_template 与 pipeline 必须非空 — C/D 的
   全部增益就是 LLM 编排, 缺一即分类错误
⑤  target / pipeline 互斥二选一 — 都空或都有即设计错误 (契约规则 1)
⑥  ServiceTarget.module 经 importlib.util.find_spec 验证真实存在 —
   注册期拦拼写错误 (只定位不 import, 无模块副作用)

附加结构规则 (契约规则 3 的步骤级机械面 + pipeline 完整性):
⑦  A/B/E 类只允许 target 单步 — pipeline 编排是 C/D 的形态
⑧  Step.kind 合法; service 步必带 target; wiki 步必带 path;
   非 llm 步不得携带 prompt_template; llm 步显式 prompt 必须非空

校验只读不写、无 DB 依赖 — find_spec 仅定位模块文件, 不执行模块代码
(不触发被检模块的 import 副作用, 如 crawl4ai 的 load_dotenv)。

失败语义: ValidationReport.errors 非空 → register() 抛
SkillRegistryValidationError 整批拒绝 — 注册期拦截, 不留"运行期才爆炸"
的坏定义; BUILTIN 单例在模块 import 期即完成校验, 违规启动直接失败。
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field

from backend.services.skill_registry.core import ServiceTarget, SkillDef, Step

__all__ = ["ValidationReport", "load_validation"]

#: 合法的 pipeline 步骤种类 (与 Step.kind Literal 保持一致)
_VALID_STEP_KINDS = ("service", "llm", "wiki")


@dataclass
class ValidationReport:
    """校验结果 — errors 非空则 register() 拒绝 (SkillRegistryValidationError)。

    每条 error 是一行人读消息 (skill id 前缀 + 违规描述), 启动日志直接可定位。
    """

    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """零违规 — True 才允许进入注册表。"""
        return not self.errors


def _check_skill(skill: SkillDef, errors: list[str], seen_ids: set[str]) -> None:
    """单 skill 六条规则 + 步骤结构校验 (内部函数, 每条违规 append 一行)。"""
    sid = skill.id or "<空 id>"

    # ① id 唯一
    if not skill.id:
        errors.append(f"{sid}: id 不能为空")
    elif skill.id in seen_ids:
        errors.append(f"{sid}: id 重复注册")
    else:
        seen_ids.add(skill.id)

    # ② feature_gate 格式与 id 自洽
    expected_gate = f"skill.{skill.id}.enabled" if skill.id else ""
    if not skill.feature_gate:
        errors.append(f"{sid}: feature_gate 不能为空 (期望 {expected_gate!r})")
    elif skill.feature_gate != expected_gate:
        errors.append(
            f"{sid}: feature_gate {skill.feature_gate!r} 与 id 不自洽 "
            f"(期望 {expected_gate!r})"
        )

    # ③ A/B/E 类不得携带 prompt_template (设计纪律 2)
    if skill.skill_type in ("A", "B", "E") and skill.prompt_template is not None:
        errors.append(f"{sid}: skill_type={skill.skill_type} 禁止 prompt_template")

    # ④ C/D 类 prompt_template + pipeline 必填
    if skill.skill_type in ("C", "D"):
        if not skill.prompt_template:
            errors.append(f"{sid}: skill_type={skill.skill_type} 缺 prompt_template")
        if not skill.pipeline:
            errors.append(f"{sid}: skill_type={skill.skill_type} 缺 pipeline")

    # ⑤ target / pipeline 互斥二选一 (都空 / 都有均违规)
    has_target = skill.target is not None
    has_pipeline = bool(skill.pipeline)
    if not has_target and not has_pipeline:
        errors.append(f"{sid}: target 与 pipeline 均为空 (必须二选一)")
    if has_target and has_pipeline:
        errors.append(f"{sid}: target 与 pipeline 同时出现 (契约规则 1)")

    # ⑦ A/B/E 只允许 target 单步直调
    if skill.skill_type in ("A", "B", "E") and has_pipeline:
        errors.append(f"{sid}: skill_type={skill.skill_type} 只允许 target 单步")

    # ⑥ ServiceTarget.module 真实存在 (find_spec, 不 import)
    _validate_service_targets(skill, errors)

    # ⑧ pipeline 步骤结构完整性 + 契约规则 3 步骤级
    for i, step in enumerate(skill.pipeline or []):
        _check_step(skill, i, step, errors)


def _validate_service_targets(skill: SkillDef, errors: list[str]) -> None:
    """规则 ⑥ — 收集 skill.target + pipeline service 步的 module 逐一 find_spec。"""
    targets: list[ServiceTarget] = []
    if isinstance(skill.target, ServiceTarget):
        targets.append(skill.target)
    for step in skill.pipeline or []:
        if step.target is not None:
            targets.append(step.target)

    for t in targets:
        spec = importlib.util.find_spec(t.module)
        if spec is None:
            errors.append(
                f"{skill.id}: ServiceTarget.module {t.module!r} 不存在 (find_spec=None)"
            )


def _check_step(skill: SkillDef, idx: int, step: Step, errors: list[str]) -> None:
    """规则 ⑧ — 单步结构: kind 合法 / 必填字段 / prompt 只在 llm 步。"""
    where = f"{skill.id}.pipeline[{idx}]"

    if step.kind not in _VALID_STEP_KINDS:
        errors.append(f"{where}: kind {step.kind!r} 非法 (合法值 {_VALID_STEP_KINDS})")
        return

    if step.kind == "service":
        if step.target is None:
            errors.append(f"{where}: service 步缺 target")
        # 契约规则 3: prompt_template 只允许出现在 llm 步
        if step.prompt_template is not None:
            errors.append(f"{where}: service 步禁止 prompt_template (仅 llm 步允许)")
    elif step.kind == "llm":
        # None = 回退 skill 级 prompt_template; 显式给出则必须非空
        if step.prompt_template is not None and not step.prompt_template:
            errors.append(f"{where}: llm 步 prompt_template 显式给出时不得为空串")
    elif step.kind == "wiki":
        if not step.path:
            errors.append(f"{where}: wiki 步缺 path 落盘模板")
        if step.prompt_template is not None:
            errors.append(f"{where}: wiki 步禁止 prompt_template (仅 llm 步允许)")


def load_validation(skills: list[SkillDef]) -> ValidationReport:
    """对整份清单执行规则 ①-⑧, 返回 ValidationReport (纯函数, 无副作用)。

    启动路径: builtin.BUILTIN 构造时 register() 内部调用本函数;
    errors 非空 → SkillRegistryValidationError, 拒绝整批注册。
    """
    errors: list[str] = []
    seen_ids: set[str] = set()
    for skill in skills:
        _check_skill(skill, errors, seen_ids)
    return ValidationReport(errors=errors)
